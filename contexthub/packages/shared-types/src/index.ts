/**
 * @contexthub/shared-types
 *
 * Single import point for every TS consumer (extension, dashboard, API clients).
 * Today: re-exports from @contexthub/interchange-spec.
 * Module 2: adds backend-generated types (DB row shapes, API request/response
 * bodies) produced by datamodel-code-generator from Pydantic → JSON Schema → TS.
 */

export * from "@contexthub/interchange-spec";
