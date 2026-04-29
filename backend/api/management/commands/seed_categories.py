from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Category

User = get_user_model()

# (name, icon, color) — Material Symbols names for frontend
SEED_CATEGORIES: list[tuple[str, str, str]] = [
    ("Regalos", "card_giftcard", "#ec4899"),
    ("Otros", "more_horiz", "#94a3b8"),
    ("Alquiler", "home", "#f59e0b"),
    ("Gastos Comunes", "apartment", "#f97316"),
    ("Luz", "bolt", "#facc15"),
    ("Agua", "water_drop", "#38bdf8"),
    ("Gas", "local_fire_department", "#fb923c"),
    ("Celular", "smartphone", "#818cf8"),
    ("Comida", "restaurant", "#84cc16"),
    ("Salidas", "nightlife", "#a78bfa"),
    ("Salidas con amalia", "favorite", "#f472b6"),
    ("Transporte", "directions_car", "#38bdf8"),
    ("Gym", "fitness_center", "#22c55e"),
    ("Pasajes Avion", "flight", "#0ea5e9"),
    ("Internet", "wifi", "#6366f1"),
    ("Limpieza casa / Nana", "cleaning_services", "#34d399"),
    ("Nafta / Bencina", "local_gas_station", "#f87171"),
    ("Consulta Medica", "medical_services", "#2dd4bf"),
    ("Remedios", "medication", "#4ade80"),
    ("Ropa", "checkroom", "#c084fc"),
    ("Online Subscriptions", "subscriptions", "#60a5fa"),
    ("Seguro Auto", "car_crash", "#fb923c"),
    ("Permiso de Circulacion", "directions_car", "#64748b"),
    ("Perro", "pets", "#d97706"),
    ("Contribuciones", "account_balance", "#64748b"),
    ("Weed", "grass", "#4ade80"),
    ("Consulta Medica Ninos", "pediatrics", "#f9a8d4"),
    ("Compras / gastos ninos", "child_care", "#fbbf24"),
    ("Tecnologia", "devices", "#2563eb"),
    ("Comida Delivery", "delivery_dining", "#f87171"),
    ("Corte de Pelo", "content_cut", "#a78bfa"),
    ("Tags Autopista", "toll", "#94a3b8"),
    ("Jardinero", "yard", "#86efac"),
    ("Piscina Mantencion", "pool", "#67e8f9"),
    ("Estacionamientos", "local_parking", "#cbd5e1"),
    ("Dividendo Condell", "real_estate_agent", "#fde68a"),
    ("Dividendo Estacion Central", "real_estate_agent", "#fde68a"),
    ("Colegio Ninos", "school", "#818cf8"),
    ("Cindes / Piscologo", "psychology", "#818cf8"),
    ("Isapre Ninos", "health_and_safety", "#34d399"),
    ("Visa Nacional", "credit_card", "#0369a1"),
    ("Visa Internacional", "credit_card", "#7c3aed"),
    ("Ahorro", "savings", "#059669"),
    ("Income", "trending_up", "#10b981"),
    ("Sueldo", "trending_up", "#10b981"),
    ("Sueldo Amalia", "trending_up", "#10b981"),
    ("Devolucion", "trending_up", "#10b981"),
]


class Command(BaseCommand):
    help = "Seed categories for a user (by email) with fixed names, icons, and colors."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email of the user to attach categories to.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all existing categories for this user before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email = (options["email"] or "").strip()
        if not email:
            raise CommandError("--email is required and must be non-empty.")

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as err:
            raise CommandError(f"No user with email {email!r} found.") from err

        if options["reset"]:
            deleted, _ = Category.objects.filter(user=user).delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted} category rows for {email}.")
            )

        created = 0
        for name, icon, color in SEED_CATEGORIES:
            _, was_created = Category.objects.update_or_create(
                user=user,
                name=name,
                defaults={"icon": icon, "color": color, "parent": None},
            )
            if was_created:
                created += 1
        updated = len(SEED_CATEGORIES) - created

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(SEED_CATEGORIES)} categories for {user.email!r} "
                f"({created} new, {updated} updated)."
            )
        )
