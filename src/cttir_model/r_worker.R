# This worker parses supplied code; it never evaluates supplied expressions.
args <- commandArgs(trailingOnly = TRUE)
emit <- function(...) cat(paste(..., sep = "\t"), "\n", sep = "")
safe <- function(value) gsub("[^A-Za-z0-9_.-]", "_", value)
mode <- args[[1L]]
if (mode == "parse") {
  value <- tryCatch(parse(file = "/input/code.R", keep.source = FALSE), error = function(e) NULL)
  if (is.null(value)) { emit("STATUS", "syntax_error"); quit(status = 0L) }
  unsupported <- FALSE
  walk <- function(node, depth = 0L) {
    if (depth > 100L) { unsupported <<- TRUE; return(invisible(NULL)) }
    if (is.expression(node)) { for (part in node) walk(part, depth + 1L); return(invisible(NULL)) }
    if (!is.call(node)) return(invisible(NULL))
    head <- node[[1L]]
    if (is.call(head) && identical(head[[1L]], as.name("::")) && length(head) == 3L &&
        is.symbol(head[[2L]]) && is.symbol(head[[3L]])) {
      pkg <- as.character(head[[2L]]); fun <- as.character(head[[3L]])
      parts <- as.list(node)[-1L]
      argument_names <- names(parts)
      if (is.null(argument_names)) argument_names <- rep("", length(parts))
      argument_names[argument_names == ""] <- "_positional"
      if (any(!grepl("^[A-Za-z_.][A-Za-z0-9_.]*$", c(pkg, fun, argument_names)))) unsupported <<- TRUE
      emit("CALL", safe(pkg), safe(fun), paste(argument_names, collapse = ","))
    } else if (is.symbol(head) && as.character(head) %in% c("<-", "{", "(", "+", "-", "*", "/", "^", ":")) {
      # These syntax nodes are parsed only; this list is not execution permission.
    } else {
      unsupported <<- TRUE
    }
    parts <- as.list(node)[-1L]
    for (i in seq_along(parts)) {
      tryCatch(walk(parts[[i]], depth + 1L), error = function(e) { unsupported <<- TRUE })
    }
  }
  walk(value)
  emit("STATUS", if (unsupported) "unsupported" else "parsed")
} else if (mode == "fixture") {
  # Fixed original synthetic fixtures only. No user-supplied code is evaluated.
  x <- data.frame(sample = c("a", "b", "c"), value = c(2, 4, 6))
  meta <- data.frame(sample = c("c", "a", "b"), donor = c("z", "x", "y"))
  joined <- merge(x, meta, by = "sample", sort = FALSE)
  stopifnot(nrow(joined) == 3L, !anyDuplicated(joined$sample), setequal(joined$sample, x$sample))
  donor <- c("a", "a", "b", "b")
  aggregated <- tapply(c(1, 3, 2, 4), donor, mean)
  stopifnot(identical(as.numeric(aggregated), c(2, 3)))
  emit("STATUS", "fixture_passed")
  emit("R_VERSION", as.character(getRversion()))
} else if (mode == "isolation") {
  stopifnot(!dir.exists("/home/rh"), !file.exists("/input/credential"),
            identical(Sys.getenv("CTTIR_SYNTHETIC_SECRET"), ""))
  net <- readLines("/proc/net/route", warn = FALSE)
  stopifnot(length(net) <= 1L)
  emit("STATUS", "isolated")
} else if (mode == "rd") {
  doc <- tryCatch(withCallingHandlers(tools::parse_Rd("/input/source.Rd", macros = FALSE),
                                       warning = function(w) stop("Invalid Rd")), error = function(e) NULL)
  if (is.null(doc)) { emit("STATUS", "rd_error"); quit(status = 0L) }
  # Flatten parsed markup, never invoke Rd2txt/Rd2HTML or evaluate Sexpr macros.
  prohibited <- FALSE
  scan <- function(node) {
    tag <- attr(node, "Rd_tag")
    if (!is.null(tag) && tag %in% c("\\Sexpr", "\\newcommand", "\\renewcommand")) prohibited <<- TRUE
    if (is.list(node)) for (part in node) scan(part)
  }
  scan(doc)
  if (prohibited) { emit("STATUS", "dynamic_rd_rejected"); quit(status = 0L) }
  cat(paste(unlist(doc, use.names = FALSE), collapse = ""))
} else stop("Unknown worker mode")
