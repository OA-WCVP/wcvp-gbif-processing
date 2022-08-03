#' Script to match all names in the GBIF backbone to accepted names in the WCVP.
#' 
#' EXPECTED INPUTS:
#'  - `output_dir`: path to a directory to save matched names to
#'  - `wcvp_file`: path to a file containing the names table from a WCVP download
#'  - `gbif_file`: path to a file containing the GBIF backbone for matching
#' 
#' EXAMPLE CLI:
#'  Rscript gbif-backbone-match.R --wcvp_file=data/wcvp_names.txt --gbif_file=data/backbone/Taxon.tsv
#' 
#' EXAMPLE SOURCE:
#'  output_dir <- "output/"
#'  wcvp_file <- data/wcvp_names.txt
#'  gbif_file <- data/backbone/Taxon.tsv
#'  source("gbif-backbone-match.R")
#' 

#  libraries ----
shhlibrary <- function(...) suppressPackageStartupMessages(library(...))
shhlibrary(tidyverse)
shhlibrary(glue)
shhlibrary(cli)

source("R/matching-functions.R")

# CLI ----

cli_h1("Matching occurrence records to species list")

if (sys.nframe() == 0L) {
  default_args <- list(
    output_dir="output/"
  )
  args <- R.utils::commandArgs(asValues=TRUE,
                               excludeReserved=TRUE, excludeEnvVars=TRUE,
                               defaults=default_args)
  
  wcvp_file <- args$wcvp_file
  gbif_file <- args$gbif_file
  output_dir <- args$output_dir
}

if (! exists("output_dir")) {
  cli_abort(c(
    "no path to save matched names",
    "x"="You must provide the save path as the variable {.var output_dir}."
  ))
}

if (! exists("wcvp_file")) {
  cli_abort(c(
    "no path to WCVP names",
    "x"="You must provide a path to a download of the WCVP taxonomy as {.var wcvp_file}."
  ))
}

if (! exists("gbif_file", mode="character")) {
  cli_abort(c(
    "no path to GBIF backbone file",
    "x"="You must provide a path to the GBIF backbone taxonomy as {.var gbif_file}."
  ))
}


cli_alert_info("Loading WCVP taxonomy from {.file {wcvp_file}}")
cli_alert_info("Loading GBIF backbone taxonomy from {.file {gbif_file}}")

dir.create(output_dir, showWarnings=FALSE)
cli_alert_info("Saving matched names to {.file {output_dir}}.")

# load taxonomies ----
cli_h2("Loading taxonomies")
wcvp_names <- read_delim(wcvp_file, delim="|", quote="", 
                         col_types=cols(.default=col_character()))

wcvp_names <-
  wcvp_names %>%
  mutate(taxon_status=ifelse(!is.na(homotypic_synonym), 
                             "Homotypic Synonym", taxon_status))

cli_alert_info("{nrow(wcvp_names)} plant names loaded from WCVP")

gbif_names <- read_tsv(gbif_file, quote="", show_col_types=FALSE)

gbif_plant_species <-
  gbif_names %>%
  filter(phylum == "Tracheophyta",
         taxonRank == "species") %>%
  filter(! str_detect(scientificName, "\\u00d7")) %>%
  mutate(name=glue("{genericName} {specificEpithet}")) %>%
  select(taxonID, scientificName, name)

cli_alert_info("{nrow(gbif_plant_species)} plant names from GBIF to match")

# match names ----
cli_h2("Matching names")

cli_h3("matching names including author strings")
gbif_matches1 <-
  gbif_plant_species %>%
  match_names_exactly(wcvp_names, id_col="taxonID", name_col="scientificName", 
                      with_author=TRUE) %>%
  filter(! is.na(match_id)) %>%
  left_join(
    gbif_plant_species %>% select(taxonID, original_name=scientificName),
    by=c("original_id"="taxonID")
  )

unmatched <-
  gbif_plant_species %>%
  filter(! scientificName %in% gbif_matches1$match_name) %>%
  distinct(taxonID, name)

cli_h3("matching names including author strings")
gbif_matches2 <-
  unmatched %>%
  match_names_exactly(wcvp_names, id_col="taxonID", name_col="name") %>%
  filter(! is.na(match_id)) %>%
  left_join(
    gbif_plant_species %>% select(taxonID, original_name=name),
    by=c("original_id"="taxonID")
  )

unmatched <-
  unmatched %>%
  filter(! name %in% gbif_matches2$match_name)

# resolve names ----
cli_h2("Resolving name matches")

resolved_matches1 <-
  gbif_matches1 %>%
  resolve_accepted_() %>%
  filter(match_status %in% c("Accepted", "Homotypic Synonym")) %>%
  resolve_multiple_matches_auto()

resolved_matches2 <-
  gbif_matches2 %>%
  resolve_accepted_() %>%
  filter(match_status %in% c("Accepted", "Homotypic Synonym")) %>%
  resolve_multiple_matches_auto()

matched_names <- bind_rows(resolved_matches1, resolved_matches2)

unmatched_names <- 
  gbif_plant_species %>%
  filter(! taxonID %in% matched_names$original_id) %>%
  select(original_id=taxonID, original_name=scientificName)

wcvp_accepted <- 
  wcvp_names %>%
  filter(taxon_status == "Accepted", taxon_rank == "Species") %>%
  filter(is.na(species_hybrid), is.na(genus_hybrid))

glue("matched {nrow(matched_names)} GBIF names to WCVP, {nrow(unmatched)} remain unmatched")
glue("{nrow(filter(wcvp_accepted, !plant_name_id %in% matched_names$accepted_id))} WCVP names (of {nrow(wcvp_accepted)}) without a match")

# save matches ----
save_file <- file.path(output_dir, "gbif-name-matches.csv")
cli_h2("Saving matching info to {.file {save_file}}")
matched_names %>%
  bind_rows(unmatched_names) %>%
  write_csv(save_file)
