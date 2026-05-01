/** Mercado Pago payment search / detail payload (subset used by the UI). */

export interface MpPaymentPaging {
  total?: number;
  limit?: number;
  offset?: number;
}

export interface MpPaymentSearchResponse {
  results: MpPayment[];
  paging?: MpPaymentPaging;
}

export interface MpIdentification {
  type?: string;
  number?: string;
}

export interface MpPayer {
  email?: string;
  id?: string;
  first_name?: string;
  last_name?: string;
  identification?: MpIdentification;
}

export interface MpCard {
  last_four_digits?: string;
  cardholder?: { name?: string };
}

export interface MpItem {
  id?: string | null;
  title?: string | null;
  description?: string | null;
  picture_url?: string | null;
  category_id?: string | null;
  /** MP API may return this as a string or number. */
  quantity?: string | number | null;
  /** MP API may return this as a string or number. */
  unit_price?: string | number | null;
  currency_id?: string | null;
}

/**
 * MercadoLibre item detail as returned by
 * GET https://api.mercadolibre.com/items?ids=...
 * (public, no auth required).
 */
export interface MlItem {
  id?: string;
  title?: string;
  price?: number;
  currency_id?: string;
  thumbnail?: string;
  condition?: string;
  category_id?: string;
  permalink?: string;
}

/** One row merged from an MpItem stub (has quantity) + MlItem detail (has title/price). */
export interface MpEnrichedItem {
  id: string;
  title: string | null;
  quantity: string | number | null;
  price: number | null;
  currency_id: string | null;
  condition: string | null;
  permalink: string | null;
}

export interface MpTransactionDetails {
  total_paid_amount?: number | null;
  net_received_amount?: number | null;
  installment_amount?: number | null;
  overpaid_amount?: number | null;
  financial_institution?: string | null;
  payment_method_reference_id?: string | null;
  acquirer_reference?: string | null;
}

export interface MpAdditionalInfo {
  items?: MpItem[] | null;
  [key: string]: unknown;
}

export interface MpPayment {
  id?: number | string;
  date_created?: string;
  date_approved?: string | null;
  description?: string | null;
  status?: string | null;
  status_detail?: string | null;
  transaction_amount?: number | null;
  currency_id?: string | null;
  payment_method_id?: string | null;
  payment_type_id?: string | null;
  payer?: MpPayer | null;
  card?: MpCard | null;
  installments?: number | null;
  net_received_amount?: number | null;
  issuer_id?: string | number | null;
  statement_descriptor?: string | null;
  merchant_order_id?: string | number | null;
  acquirer_id?: number | string | null;
  operation_type?: string | null;
  additional_info?: MpAdditionalInfo | null;
  transaction_details?: MpTransactionDetails | null;
  shipping_amount?: number | null;
  coupon_amount?: number | null;
  taxes_amount?: number | null;
}
