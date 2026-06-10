export type {
  Artifact,
  AttachmentRefPart,
  CodeBlockPart,
  ConversationV0,
  Decision,
  ImageRefPart,
  Message,
  MessageContent,
  Metadata,
  OpenQuestion,
  Source,
  StructuredBlockV0,
  TextPart,
  ToolUsePart,
} from "./models.js";

export { renderStructuredBlock } from "./renderer.js";
export { makeValidator, validateConversation, validateStructuredBlock } from "./ajv.js";

export const SPEC_VERSION = "ch.v0.1" as const;
