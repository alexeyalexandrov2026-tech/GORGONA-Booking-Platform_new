import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  agreementHistorySchema,
  agreementListSchema,
  agreementSchema,
  type AgreementCommand,
} from "./agreement-contracts";

const base = (business: string) => `/v1/businesses/${business}`;

async function read<T extends { business_id: string; agreement_id?: string }>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  subject?: string,
  init?: RequestInit,
): Promise<T> {
  const result = schema.parse(await managementFetch(path, init));
  if (
    result.business_id !== business ||
    (subject && result.agreement_id !== subject)
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this contract safely.",
    );
  return result;
}

export async function fetchAgreements(
  business: string,
  counterparty: string,
  after?: string,
) {
  const result = await read(
    business,
    agreementListSchema,
    `${base(business)}/counterparties/${counterparty}/agreements${after ? `?after=${after}` : ""}`,
  );
  if (result.counterparty_id !== counterparty)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load contracts safely.",
    );
  return result;
}
export async function fetchAgreement(
  business: string,
  subject: string,
  revision?: number,
) {
  const result = await read(
    business,
    agreementSchema,
    `${base(business)}/agreements/${subject}${revision ? `?revision=${revision}` : ""}`,
    subject,
  );
  if (revision && result.revision !== revision)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this saved version safely.",
    );
  return result;
}
export function fetchAgreementHistory(
  business: string,
  subject: string,
  before?: number,
) {
  return read(
    business,
    agreementHistorySchema,
    `${base(business)}/agreements/${subject}/versions${before ? `?before=${before}` : ""}`,
    subject,
  );
}
export function executeAgreementCommand(
  business: string,
  command: AgreementCommand,
) {
  const path = `${base(business)}/agreements/${command.id}`;
  const init = {
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  return command.type === "draft"
    ? read(business, agreementSchema, path, command.id, {
        ...init,
        method: "PUT",
      })
    : read(business, agreementSchema, `${path}/${command.type}`, command.id, {
        ...init,
        method: "POST",
      });
}
