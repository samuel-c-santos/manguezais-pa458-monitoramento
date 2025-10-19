# ------------------------------------------------------------
# BFAST em NDVI mensal (PA-458, Leste/Oeste) — FINAL ROBUSTO
# ------------------------------------------------------------
library(bfast)
library(tidyverse)
library(lubridate)
library(zoo)
library(gridExtra)
library(grid)
library(forecast)     # para na.interp (preencher NAs, inclusive bordas)
library(strucchange)  # fallback: quebras na tendência (Tt)

# 1) Leitura
setwd("H:/Meu Drive/UFRA/PRÉ PROJETO DE TCC/PRODUTOS TCC")

df <- readr::read_csv("PA458_NDVI_mensal_2017_2025_12km.csv", show_col_types = FALSE) |>
  dplyr::mutate(date = as.Date(paste0(date, "-01"))) |>
  dplyr::arrange(lado, date)

print(table(df$lado, useNA = "ifany"))
print(range(df$date, na.rm = TRUE))
stopifnot(all(c("Leste","Oeste") %in% unique(df$lado)))

# 2) Série mensal SEM NAs
build_ts <- function(df_side, lado_nome) {
  x <- df_side |>
    dplyr::filter(lado == lado_nome) |>
    tidyr::complete(date = seq.Date(min(date), max(date), by = "month")) |>
    dplyr::arrange(date)
  
  y_ts <- ts(x$ndvi,
             frequency = 12,
             start = c(lubridate::year(min(x$date)), lubridate::month(min(x$date))))
  forecast::na.interp(y_ts)
}

ts_e <- build_ts(df, "Leste")
ts_w <- build_ts(df, "Oeste")
cat("NAs em Leste:", sum(is.na(ts_e)), " | NAs em Oeste:", sum(is.na(ts_w)), "\n")

# 3) BFAST — VARREDURA
h_varredura <- 0.20
res_e <- bfast(ts_e, h = h_varredura, season = "harmonic", max.iter = 5)
res_w <- bfast(ts_w, h = h_varredura, season = "harmonic", max.iter = 5)

png("bfast_Leste_varredura.png", width = 1800, height = 1200, res = 180);  plot(res_e, main = "BFAST — Leste (varredura)");  dev.off()
png("bfast_Oeste_varredura.png", width = 1800, height = 1200, res = 180);  plot(res_w, main = "BFAST — Oeste (varredura)");  dev.off()

# 4) BFAST MONITOR — histórico 2017–2018, start=2019-01
t0 <- c(2019, 1)
h_monitor <- 0.25

mon_e <- bfastmonitor(ts_e, start = t0, formula = response ~ season + trend, h = h_monitor, order = 0)
mon_w <- bfastmonitor(ts_w, start = t0, formula = response ~ season + trend, h = h_monitor, order = 0)

png("bfastmonitor_Leste.png", width = 1800, height = 1200, res = 180);  plot(mon_e, main = "BFAST Monitor — Leste (pós-2019)");  dev.off()
png("bfastmonitor_Oeste.png", width = 1800, height = 1200, res = 180);  plot(mon_w, main = "BFAST Monitor — Oeste (pós-2019)");  dev.off()

# ===== Helpers comuns =====
idx_to_date <- function(ts_obj, idx_vec) {
  tv <- time(ts_obj)
  yr <- floor(tv)
  mo <- round((tv - yr) * frequency(ts_obj) + 1)
  mo[mo == (frequency(ts_obj) + 1)] <- frequency(ts_obj)
  as.Date(paste(yr, mo, "01", sep = "-"))[idx_vec]
}

# ---- varredura: tenta breakpoints do objeto; fallback = strucchange em Tt ----
extract_varredura_breaks <- function(bres, lado_nm) {
  rows <- list()
  # 1) tentar todos os "output" nativos
  if (!is.null(bres$output) && length(bres$output) > 0) {
    for (o in bres$output) {
      if (is.null(o) || is.null(o$breakpoints)) next
      bp_idx <- o$breakpoints
      if (length(bp_idx) == 0 || all(is.na(bp_idx))) next
      Tt <- o$Tt
      mags <- sapply(bp_idx, function(i) if (is.finite(i) && i < length(Tt)) Tt[i + 1] - Tt[i] else NA_real_)
      rows[[length(rows)+1]] <- tibble(
        lado = lado_nm, tipo = "varredura", date = idx_to_date(bres$Yt, bp_idx), magnitude = as.numeric(mags)
      )
    }
  }
  out_tbl <- if (length(rows)) bind_rows(rows) else tibble()
  
  # 2) fallback: breakpoints na Tt (tendência) via strucchange
  # pega primeira Tt válida
  get_Tt_ts <- function(bres) {
    if (is.null(bres$output) || !length(bres$output)) return(NULL)
    for (o in bres$output) if (!is.null(o$Tt)) {
      return(ts(o$Tt, frequency = frequency(bres$Yt), start = start(bres$Yt)))
    }
    NULL
  }
  Tt_ts <- get_Tt_ts(bres)
  if (!is.null(Tt_ts)) {
    bp <- breakpoints(Tt_ts ~ 1)  # escolhe nº de quebras por BIC
    idx <- na.omit(as.integer(bp$breakpoints))
    if (length(idx) > 0) {
      fac <- breakfactor(bp)
      seg_means <- aggregate(as.numeric(Tt_ts), by = list(seg = fac), FUN = mean)
      mags <- diff(seg_means$x)
      fallback_tbl <- tibble(
        lado = lado_nm, tipo = "varredura-trend", date = idx_to_date(Tt_ts, idx), magnitude = as.numeric(mags)
      )
      # combina, evitando duplicatas na mesma data/tipo
      out_tbl <- bind_rows(out_tbl, fallback_tbl) |>
        arrange(lado, tipo, date) |>
        distinct(lado, tipo, date, .keep_all = TRUE)
    }
  }
  out_tbl
}

# ---- monitor: tenta vários campos conhecidos ----
extract_monitor_breaks <- function(mon, lado_nm) {
  cand <- list(mon$breakpoints, mon$breakpoint, mon$mph$breakpoint, mon$bp.Vt$breakpoints)
  bp <- NULL
  for (c in cand) if (!is.null(c)) { bp <- c; break }
  if (is.null(bp)) return(tibble())
  if (inherits(bp, "Date")) {
    dts <- bp
  } else if (is.numeric(bp)) {
    ts_base <- if (!is.null(mon$Yt)) mon$Yt else NULL
    dts <- if (!is.null(ts_base)) idx_to_date(ts_base, as.integer(bp)) else as.Date(character())
  } else dts <- as.Date(character())
  tibble(lado = lado_nm, tipo = "monitor", date = dts,
         magnitude = if (!is.null(mon$magnitude)) as.numeric(mon$magnitude) else NA_real_)
}

# 5) Aplicar
bk_e  <- extract_varredura_breaks(res_e, "Leste")
bk_w  <- extract_varredura_breaks(res_w, "Oeste")
bk_me <- extract_monitor_breaks(mon_e, "Leste")
bk_mw <- extract_monitor_breaks(mon_w, "Oeste")

bk_all <- bind_rows(bk_e, bk_w, bk_me, bk_mw) |>
  arrange(lado, tipo, date) |>
  distinct(lado, tipo, date, .keep_all = TRUE)

# 6) Exportar CSV
write_csv(bk_all, "bfast_quebras_datas_magnitudes.csv")

# 7) Tabela PNG (robusta a 0 linhas)
make_table_png <- function(tbl, fname, title = NULL) {
  if (nrow(tbl) == 0) {
    tbl_fmt <- tibble(lado = "—", tipo = "—", date = "—", magnitude = "—")
  } else {
    tbl_fmt <- tbl |>
      mutate(date = ifelse(is.na(date), NA, format(date, "%Y-%m")),
             magnitude = round(magnitude, 3))
  }
  g <- gridExtra::tableGrob(
    tbl_fmt, rows = NULL,
    theme = gridExtra::ttheme_minimal(
      core   = list(fg_params = list(cex = 0.9)),
      colhead= list(fg_params = list(fontface = 2))
    )
  )
  if (!is.null(title)) {
    title_g <- grid::textGrob(title, gp = grid::gpar(fontface = "bold", cex = 1.05))
    g <- gridExtra::arrangeGrob(title_g, g,
                                heights = grid::unit.c(grid::grobHeight(title_g) + grid::unit(4, "mm"),
                                                       grid::unit(1, "null")))
  }
  ggsave(filename = fname, g, width = 9, height = 5.5, dpi = 300)
}

make_table_png(
  bk_all,
  "bfast_quebras_datas_magnitudes.png",
  title = "Quebras detectadas (varredura/monitor) — PA-458 (NDVI mensal)"
)
