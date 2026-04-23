import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import (
    Category,
    Direction,
    Frequency,
    RecurringPattern,
    Source,
    Transaction,
    TransactionStatus,
    TransactionType,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed finance models with mock data for a user."

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, default="seed_user")
        parser.add_argument("--email", type=str, default="seed_user@example.com")
        parser.add_argument("--password", type=str, default="SeedPass123!")
        parser.add_argument("--categories", type=int, default=8)
        parser.add_argument("--transactions", type=int, default=40)
        parser.add_argument("--patterns", type=int, default=5)
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing finance data for that user before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={"email": options["email"]},
        )
        if created:
            user.set_password(options["password"])
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Created user: {user.username}"))
        else:
            self.stdout.write(f"Using existing user: {user.username}")

        if options["reset"]:
            Transaction.objects.filter(user=user).delete()
            RecurringPattern.objects.filter(user=user).delete()
            Category.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING("Existing user finance data deleted."))

        categories = self._create_categories(user, options["categories"])
        transactions = self._create_transactions(user, categories, options["transactions"])
        patterns = self._create_recurring_patterns(user, categories, options["patterns"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed completed. Categories={len(categories)} "
                f"Transactions={transactions} Patterns={patterns}"
            )
        )

    def _create_categories(self, user, total):
        base_names = [
            "Food",
            "Transport",
            "Housing",
            "Health",
            "Entertainment",
            "Utilities",
            "Shopping",
            "Savings",
        ]
        categories = []
        for index in range(total):
            name = base_names[index % len(base_names)]
            category = Category.objects.create(
                user=user,
                name=f"{name} {index + 1}" if total > len(base_names) else name,
                icon="circle",
                color=random.choice(["#FF5733", "#33A1FF", "#33CC99", "#AA66CC"]),
            )
            categories.append(category)

        if len(categories) >= 2:
            categories[1].parent = categories[0]
            categories[1].save(update_fields=["parent"])

        return categories

    def _create_transactions(self, user, categories, total):
        now = timezone.now()
        descriptions = [
            "Uber ride",
            "Supermarket purchase",
            "Salary payment",
            "Coffee shop",
            "Card installment",
            "Electricity bill",
            "Insurance payment",
        ]
        sources = list(Source.values)
        created = 0

        for index in range(total):
            direction = random.choice([Direction.EXPENSE, Direction.INCOME])
            tx_type = (
                TransactionType.CREDIT if direction == Direction.INCOME else TransactionType.DEBIT
            )
            source = random.choice(sources)
            is_installment = source in {
                Source.CREDIT_CARD_NATIONAL,
                Source.CREDIT_CARD_INTERNATIONAL,
            } and random.choice([True, False])
            installment_total = random.randint(2, 12) if is_installment else None
            installment_current = (
                random.randint(1, installment_total) if installment_total else None
            )
            amount = Decimal(str(round(random.uniform(5, 400), 2)))

            Transaction.objects.create(
                user=user,
                description=random.choice(descriptions),
                amount=amount,
                currency=random.choice(["CLP", "USD"]),
                amount_local=amount if random.choice([True, False]) else None,
                exchange_rate=Decimal("1.000000")
                if random.choice([True, False])
                else None,
                transaction_type=tx_type,
                direction=direction,
                category=random.choice(categories),
                subcategory=random.choice(["General", "Premium", "Basic", None]),
                source=source,
                original_reference=f"ref-{index + 1}",
                external_id=f"{source.lower()}-{index + 1}",
                is_installment=is_installment,
                installment_current=installment_current,
                installment_total=installment_total,
                installment_amount=(
                    (amount / installment_total).quantize(Decimal("0.01"))
                    if installment_total
                    else None
                ),
                installment_group_id=uuid.uuid4() if is_installment else None,
                raw_data={"seeded": True, "index": index + 1},
                imported_at=now - timedelta(days=random.randint(0, 60)),
                status=random.choice(list(TransactionStatus.values)),
            )
            created += 1

        return created

    def _create_recurring_patterns(self, user, categories, total):
        labels = ["Netflix", "Rent", "Gym", "Spotify", "Internet", "Phone plan"]
        frequencies = list(Frequency.values)
        created = 0

        for index in range(total):
            RecurringPattern.objects.create(
                user=user,
                description_pattern=labels[index % len(labels)],
                category=random.choice(categories),
                expected_amount=Decimal(str(round(random.uniform(8, 100), 2))),
                frequency=random.choice(frequencies),
            )
            created += 1

        return created
