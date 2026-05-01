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
}
