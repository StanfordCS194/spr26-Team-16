/**
 * @contexthub/shared-types
 *
 * Single import point for every TS consumer (extension, dashboard, API clients).
 * Exports:
 *  - interchange-spec types (ch.v0.1 conversation + structured-block models)
 *  - DB row types for all §5 tables (API response shapes)
 */

export * from "@contexthub/interchange-spec";
export * from "./db-types";
