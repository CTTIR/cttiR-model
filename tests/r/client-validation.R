source("r/client.R")
expect_typed <- function(expr, code) {
  error <- tryCatch(force(expr), error = identity)
  stopifnot(inherits(error, paste0("cttir_model_", code)))
}
context <- list(request_id = "validation", language = "en", instruction = "Explain alignment",
                corpus_id = "fixture", package_pins = list(), evidence_ids = list("evidence"),
                input_contract = list(columns = list(), object_classes = list(), experimental_unit = "sample"))
expect_typed(cttir_model_health("http://127.0.0.1:65536"), "endpoint")
expect_typed(cttir_model_health(NA_character_), "endpoint")
bad <- context
bad$input_contract <- 1
expect_typed(cttir_model_consult("explain_api", bad), "request")
bad <- context
bad$instruction <- NA_character_
expect_typed(cttir_model_consult("explain_api", bad), "request")
expect_typed(cttir_model_consult("explain_api", c(context, context[1])), "request")
response <- list(proposal = list(protocol_version = 1L, request_id = "validation", status = "proposed",
                                summary = "Fixture", r_code = NULL, evidence_ids = list("evidence"),
                                assumptions = list(), missing_inputs = list(), limitations = list()),
                 verification = list(schema_valid = TRUE, evidence_pins_valid = TRUE, r_execution_authorized = FALSE),
                 corpus_id = "fixture")
cttir_model_http <- function(...) response
stopifnot(identical(cttir_model_consult("explain_api", context), response))
for (field in c("schema_valid", "evidence_pins_valid")) {
  response$verification[[field]] <- FALSE
  expect_typed(cttir_model_consult("explain_api", context), "protocol")
  response$verification[[field]] <- TRUE
}
response$proposal$evidence_ids <- list()
expect_typed(cttir_model_consult("explain_api", context), "protocol")
response$proposal$evidence_ids <- list("evidence", "evidence")
expect_typed(cttir_model_consult("explain_api", context), "protocol")
response$proposal$evidence_ids <- list("unrequested")
expect_typed(cttir_model_consult("explain_api", context), "protocol")
cat("R client input and response validation passed\n")
