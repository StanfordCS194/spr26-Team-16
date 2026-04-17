import Ajv, { type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import conversationSchema from "../schemas/ch.v0.1.conversation.json" with { type: "json" };
import structuredBlockSchema from "../schemas/ch.v0.1.structured-block.json" with { type: "json" };
import type { ConversationV0, StructuredBlockV0 } from "./models.js";

type SchemaKind = "conversation" | "structured-block";

export function makeValidator(kind: SchemaKind): ValidateFunction {
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);
  const schema = kind === "conversation" ? conversationSchema : structuredBlockSchema;
  return ajv.compile(schema);
}

const conversationValidator = makeValidator("conversation");
const structuredBlockValidator = makeValidator("structured-block");

export function validateConversation(obj: unknown): obj is ConversationV0 {
  return conversationValidator(obj);
}

export function validateStructuredBlock(obj: unknown): obj is StructuredBlockV0 {
  return structuredBlockValidator(obj);
}
