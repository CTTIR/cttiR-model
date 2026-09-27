source("r/client.R")
args <- commandArgs(trailingOnly = TRUE)
endpoint <- args[[1L]]
health <- cttir_model_health(endpoint)
stopifnot(isFALSE(health$model_ready), identical(health$mode, "fixture"))
context <- list(request_id = "r-client-fixture", language = "en", instruction = "Explain alignment",
                corpus_id = args[[2L]], package_pins = list(list(name = "fixtureR", version = "1.0", repository = "synthetic")),
                evidence_ids = list("evidence-v1"),
                input_contract = list(columns = list(), object_classes = list(), experimental_unit = "sample"))
result <- cttir_model_consult("explain_api", context, endpoint)
stopifnot(identical(result$proposal$status, "proposed"), isFALSE(result$verification$r_execution_authorized))
stopifnot(identical(result, cttir_model_consult("explain_api", context, endpoint)))
context$corpus_id <- "wrong"
err <- tryCatch(cttir_model_consult("explain_api", context, endpoint), error = identity)
stopifnot(inherits(err, "cttir_model_error"))
err <- tryCatch(cttir_model_health("https://example.org"), error = identity)
stopifnot(inherits(err, "cttir_model_endpoint"))
cat("R client integration passed\n")
