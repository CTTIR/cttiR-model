# Thin protocol-v1 client. Source this file; no GPU runtime or reticulate.
cttir_model_error <- function(code, message) {
  stop(structure(list(message = message, call = NULL, code = code),
                 class = c(paste0("cttir_model_", code), "cttir_model_error", "error", "condition")))
}

cttir_model_http <- function(path, endpoint, timeout, body = NULL, method = "GET") {
  if (!is.character(endpoint) || length(endpoint) != 1L ||
      !grepl("^http://127[.]0[.]0[.]1:[0-9]{1,5}$", endpoint)) {
    cttir_model_error("endpoint", "Use a literal loopback endpoint without credentials or a path.")
  }
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
  if (response$status_code != 200L) {
    code <- value$error$code
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
  if (!is.character(task) || length(task) != 1L || !task %in% tasks || !is.list(context)) {
    cttir_model_error("request", "Supply a supported task and structured context list.")
  }
  required <- c("request_id", "language", "instruction", "corpus_id", "package_pins", "evidence_ids", "input_contract")
  if (!setequal(names(context), required)) cttir_model_error("request", "Context must contain exactly the protocol-v1 fields.")
  for (name in c("request_id", "language", "instruction", "corpus_id")) {
    if (!is.character(context[[name]]) || length(context[[name]]) != 1L || !nzchar(context[[name]])) {
      cttir_model_error("request", "Request text fields must be nonempty scalar strings.")
    }
  }
  context$evidence_ids <- as.list(context$evidence_ids)
  context$package_pins <- as.list(context$package_pins)
  context$input_contract$columns <- as.list(context$input_contract$columns)
  context$input_contract$object_classes <- as.list(context$input_contract$object_classes)
  body <- c(list(protocol_version = 1L, task = task), context,
            list(budget = list(max_output_tokens = 512L, timeout_seconds = as.integer(timeout))))
  value <- cttir_model_http("/v1/consult", endpoint, timeout, body, "POST")
  proposal <- value$proposal
  if (!is.list(proposal) || !identical(proposal$protocol_version, 1L) ||
      !identical(proposal$request_id, context$request_id) ||
      !proposal$status %in% c("proposed", "needs_input", "unsupported", "failed") ||
      !is.null(proposal$r_code) || !isFALSE(value$verification$r_execution_authorized)) {
    cttir_model_error("protocol", "Unvalidated or incompatible service response.")
  }
  value
}

cttir_model_cancel <- function(request_id, endpoint = "http://127.0.0.1:8088", timeout = 5) {
  if (!is.character(request_id) || length(request_id) != 1L || !nzchar(request_id)) {
    cttir_model_error("request", "request_id must be a nonempty string.")
  }
  cttir_model_http(paste0("/v1/requests/", utils::URLencode(request_id, reserved = TRUE)),
                   endpoint, timeout, method = "DELETE")
}
