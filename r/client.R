# Thin protocol-v1 client. Source this file; no GPU runtime or reticulate.
cttir_model_error <- function(code, message) {
  stop(structure(list(message = message, call = NULL, code = code),
                 class = c(paste0("cttir_model_", code), "cttir_model_error", "error", "condition")))
}

cttir_model_text <- function(value) {
  is.character(value) && length(value) == 1L && is.null(dim(value)) &&
    !is.na(value) && nzchar(value)
}

cttir_model_http <- function(path, endpoint, timeout, body = NULL, method = "GET") {
  if (!cttir_model_text(endpoint) ||
      !grepl("^http://127[.]0[.]0[.]1:[0-9]{1,5}$", endpoint)) {
    cttir_model_error("endpoint", "Use a literal loopback endpoint without credentials or a path.")
  }
  port <- as.integer(sub("^.*:", "", endpoint))
  if (port < 1L || port > 65535L) cttir_model_error("endpoint", "Loopback port must be between 1 and 65535.")
  if (!is.numeric(timeout) || length(timeout) != 1L || !is.finite(timeout) || timeout < 1 || timeout > 60) {
    cttir_model_error("timeout", "timeout must be between 1 and 60 seconds.")
  }
  for (pkg in c("curl", "jsonlite")) {
    if (!requireNamespace(pkg, quietly = TRUE)) cttir_model_error("dependency", paste("Install declared dependency", pkg))
  }
  handle <- curl::new_handle(timeout = timeout, connecttimeout = min(timeout, 5),
                             followlocation = FALSE, proxy = "", customrequest = method)
  curl::handle_setheaders(handle, "Accept" = "application/json")
  if (!is.null(body)) {
    encoded <- jsonlite::toJSON(body, auto_unbox = TRUE, null = "null", digits = NA)
    if (nchar(encoded, type = "bytes") > 65536) cttir_model_error("input_limit", "Request exceeds 64 KiB.")
    curl::handle_setheaders(handle, "Content-Type" = "application/json", "Accept" = "application/json")
    curl::handle_setopt(handle, postfields = encoded)
  }
  buffer <- raw()
  response <- tryCatch(curl::curl_fetch_stream(paste0(endpoint, path), function(chunk) {
    if (length(buffer) + length(chunk) > 131072) cttir_model_error("output_limit", "Response exceeds 128 KiB.")
    buffer <<- c(buffer, chunk)
  }, handle = handle), error = function(e) {
    if (inherits(e, "cttir_model_error")) stop(e)
    cttir_model_error("transport", "Local service is unavailable or the request timed out.")
  })
  value <- tryCatch(jsonlite::fromJSON(rawToChar(buffer), simplifyVector = FALSE),
                    error = function(e) cttir_model_error("protocol", "Service returned invalid JSON."))
  if (!is.list(value) || is.null(names(value))) cttir_model_error("protocol", "Service JSON must be an object.")
  if (response$status_code != 200L) {
    code <- if (is.list(value$error)) value$error$code else NULL
    if (!is.character(code) || length(code) != 1L || !grepl("^[a-z_]+$", code)) code <- "http"
    cttir_model_error(code, paste("Local service rejected the request (HTTP", response$status_code, ")."))
  }
  value
}

cttir_model_health <- function(endpoint = "http://127.0.0.1:8088", timeout = 5) {
  value <- cttir_model_http("/health", endpoint, timeout)
  if (!identical(value$protocol_version, 1L) || !is.logical(value$model_ready) ||
      length(value$model_ready) != 1L) cttir_model_error("protocol", "Incompatible health response.")
  value
}

cttir_model_consult <- function(task, context, endpoint = "http://127.0.0.1:8088", timeout = 30) {
  tasks <- c("select_workflow", "propose_r_code", "explain_api", "review_r_code")
  if (!cttir_model_text(task) || !task %in% tasks || !is.list(context)) {
    cttir_model_error("request", "Supply a supported task and structured context list.")
  }
  required <- c("request_id", "language", "instruction", "corpus_id", "package_pins", "evidence_ids", "input_contract")
  if (length(context) != length(required) || !setequal(names(context), required)) {
    cttir_model_error("request", "Context must contain exactly the protocol-v1 fields.")
  }
  for (name in c("request_id", "language", "instruction", "corpus_id")) {
    if (!cttir_model_text(context[[name]])) {
      cttir_model_error("request", "Request text fields must be nonempty scalar strings.")
    }
  }
  fields <- c("columns", "object_classes", "experimental_unit")
  if (!is.list(context$input_contract) || length(context$input_contract) != length(fields) ||
      !setequal(names(context$input_contract), fields)) {
    cttir_model_error("request", "input_contract must contain columns, object_classes and experimental_unit.")
  }
  context$evidence_ids <- as.list(context$evidence_ids)
  context$package_pins <- as.list(context$package_pins)
  context$input_contract$columns <- as.list(context$input_contract$columns)
  context$input_contract$object_classes <- as.list(context$input_contract$object_classes)
  body <- c(list(protocol_version = 1L, task = task), context,
            list(budget = list(max_output_tokens = 512L, timeout_seconds = as.integer(timeout))))
  value <- cttir_model_http("/v1/consult", endpoint, timeout, body, "POST")
  proposal <- value$proposal
  proposal_fields <- c("protocol_version", "request_id", "status", "summary", "r_code", "evidence_ids",
                        "assumptions", "missing_inputs", "limitations")
  if (!is.list(proposal) || !identical(proposal$protocol_version, 1L) ||
      !identical(proposal$request_id, context$request_id) ||
      length(proposal) != length(proposal_fields) || !setequal(names(proposal), proposal_fields) ||
      !cttir_model_text(proposal$status) ||
      !proposal$status %in% c("proposed", "needs_input", "unsupported", "failed") ||
      !cttir_model_text(proposal$summary) ||
      !is.null(proposal$r_code) || !is.list(value$verification) ||
      !isTRUE(value$verification$schema_valid) || !isTRUE(value$verification$evidence_pins_valid) ||
      !isFALSE(value$verification$r_execution_authorized) || !identical(value$corpus_id, context$corpus_id)) {
    cttir_model_error("protocol", "Unvalidated or incompatible service response.")
  }
  for (name in c("evidence_ids", "assumptions", "missing_inputs", "limitations")) {
    items <- proposal[[name]]
    if (!is.list(items) || !is.null(names(items)) || !all(vapply(items, cttir_model_text, logical(1)))) {
      cttir_model_error("protocol", "Proposal array fields are invalid.")
    }
  }
  if (anyDuplicated(proposal$evidence_ids) ||
      (proposal$status == "proposed" && !length(proposal$evidence_ids)) ||
      !all(unlist(proposal$evidence_ids) %in% unlist(context$evidence_ids))) {
    cttir_model_error("protocol", "Response cited evidence outside the request.")
  }
  value
}

cttir_model_cancel <- function(request_id, endpoint = "http://127.0.0.1:8088", timeout = 5) {
  if (!cttir_model_text(request_id)) {
    cttir_model_error("request", "request_id must be a nonempty string.")
  }
  cttir_model_http(paste0("/v1/requests/", utils::URLencode(request_id, reserved = TRUE)),
                   endpoint, timeout, method = "DELETE")
}
