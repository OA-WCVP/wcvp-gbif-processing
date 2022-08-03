#' Functions for matching and resolving a dataframe of names to WCVP.
#' 


#' Match names to WCVP taxonomy.
#' 
#' Match names from a column in a dataframe of taxon names to names in the World
#' Checklist of Vascular Plants. Names are matched exactly using a join.
#' 
#' @param names_df A dataframe of with a column of taxon names for matching.
#' @param wcvp A dataframe of the WCVP names table.
#' @param name_col The name of the column storing the taxon names.
#' @param match_rank A string specifying the taxonomic rank to match at, e.g. "Species".
#' @param with_author Whether the names to match include the author string or not.
#' 
#' @return A dataframe mapping the original names to any matches from the WCVP.
#'
match_names_exactly <- function(names_df, wcvp, id_col="id", name_col="name", 
                                match_rank=NULL, with_author=FALSE) {
  if (! is.null(match_rank)) {
    wcvp <- filter(wcvp, taxon_rank == match_rank)
  }
  
  if (with_author) {
    wcvp$taxon_name <- glue::glue("{wcvp$taxon_name} {wcvp$taxon_authors}")
  }
  
  named_cols <- c(
    "original_id"=id_col, "match_name"=name_col, "match_id"="plant_name_id", 
    "match_rank"="taxon_rank", "match_authors"="taxon_authors", 
    "match_status"="taxon_status", "accepted_id"="accepted_plant_name_id"
  )
  
  matches <-
    names_df %>%
    left_join(wcvp, by=setNames("taxon_name", name_col)) %>%
    select(!!! named_cols) %>%
    left_join(
      wcvp %>% select(plant_name_id, accepted_name=taxon_name, 
                      accepted_authors=taxon_authors, accepted_rank=taxon_rank),
      by=c("accepted_id"="plant_name_id")
    )
  
  multiple_matches <- 
    matches %>%
    count(original_id) %>%
    filter(n > 1) %>%
    nrow()
  
  matched_names <-
    matches %>%
    filter(!is.na(match_id)) %>%
    count(original_id) %>%
    nrow()
  
  unmatched_names <-
    matches %>%
    filter(is.na(match_id)) %>%
    count(original_id) %>%
    nrow()
  
  cli::cli_alert_success("{matched_names} of {nrow(names_df)} name{?s} matched to WCVP")
  if (multiple_matches > 0) {
    cli::cli_alert_warning("{multiple_matches} matched to multiple names")  
  } 
  
  if (unmatched_names > 0) {
    cli::cli_alert_warning("{unmatched_names} name{?s} left unmatched")
  }
  
  matches
}


#' Resolve matched names to WCVP accepted names.
#'
#' Fill out the accepted taxon info columns of a match dataframe. These stay the
#' same if the matched name is a homotypic synonym or orthographic variant, but 
#' are copied across from the match info columns if the match name is already
#' accepted. Any matches with a different taxonomic status are set to blank.
#'
#' @param info A dataframe with name matches, probably output from the 
#'   `match_names_exactly` function.
#'   
#' @return The same dataframe with the accepted info columns completed.
#' 
resolve_accepted_ <- function(info) {
  info %>%
    mutate(accepted_id=case_when(match_status == "Accepted" ~ match_id,
                                 match_status == "Homotypic Synonym" ~ accepted_id,
                                 match_status == "Orthographic" ~ accepted_id,
                                 TRUE ~ NA_character_),
           accepted_name=case_when(match_status == "Accepted" ~ match_name,
                                   match_status == "Homotypic Synonym" ~ accepted_name,
                                   TRUE ~ NA_character_),
           accepted_authors=case_when(match_status == "Accepted" ~ match_authors,
                                      match_status == "Homotypic Synonym" ~ accepted_authors,
                                      match_status == "Orthographic" ~ accepted_authors,
                                      TRUE ~ NA_character_),
           accepted_rank=case_when(match_status == "Accepted" ~ match_rank,
                                   match_status == "Homotypic Synonym" ~ accepted_rank,
                                   match_status == "Orthographic" ~ accepted_rank,
                                   TRUE ~ NA_character_))
}

#' Resolve multiple matches for one original name.
#' 
#' Attempts to find a single name match for a set of names matched to one 
#' original name. First, if the name is infraspecific, names at a different 
#' level are discarded. Second, if there is a single accepted name, all other matches
#' are discarded. Third, if there is a single orthographic variant, all other matches
#' are discarded. Fourth, if there is a single homotypic synonym, all other matches 
#' are discarded. Finally, if there is still more than one match, all matches are returned.
#' 
#' @param matches A dataframe of name matches for a single original name.
#' @param original_name A string specifying the original name that has multiple matches.
#' 
#' @return A dataframe of a single match if successful, otherwise of all the matches.
#' 
resolve_multi_ <- function(matches, original_name) {
  if (! "match_status" %in% colnames(matches)) {
    stop("Information about taxonomic status of matches is needed but not present.")
  }
  
  # don't need to resolve if there's only one match
  if (nrow(matches) <= 1) {
    return(matches)
  }
  
  resolved_matches <- matches
  
  # 1. if the name to match is an infraspecific, take the match with the right rank
  
  # first need to extract the rank, and make sure the subspecies abbreviation matches
  rank <- str_extract(original_name, "(?<= )(var\\.|ssp\\.|subsp\\.|f.)(?= )")
  rank <- str_replace(rank, "ssp\\.", "subsp\\.")
  
  if (! is.na(rank)) {
    rank_regex <- paste0(" ", rank, " ")
    resolved_matches <- dplyr::filter(resolved_matches, 
                                      str_detect(match_name, rank_regex))
  }
  
  if (nrow(resolved_matches) == 1) {
    return(resolved_matches)
  }
  
  # 2. If there is an accepted name present, resolve to that
  resolved_matches <- dplyr::filter(resolved_matches, 
                                    match_status == "Accepted" | all(match_status != "Accepted"))
  
  if (nrow(resolved_matches) == 1) {
    return(resolved_matches)
  }
  
  # 3. otherwise resolve to orthographic variant, if it's there
  resolved_matches <- dplyr::filter(resolved_matches, 
                                    match_status == "Orthographic" | all(match_status != "Orthographic"))
  
  if (nrow(resolved_matches) == 1) {
    return(resolved_matches)
  }
  
  # 4. If there is a homotypic synonym present, resolve to that
  if ("homotypic_synonym" %in% colnames(matches)) {
    # this is necessary because the WCVP data changed format
    resolved_matches <- dplyr::filter(resolved_matches, ! is.na(homotypic_synonym) | all(! is.na(homotypic_synonym)))
  } else {
    resolved_matches <- dplyr::filter(resolved_matches, match_status == "Homotypic Synonym" | all(match_status != "Homotypic Synonym"))  
  }
  
  # return resolved data, if nothing worked it will be returned unchanged
  resolved_matches
}


#' Resolve all multiple matches in a dataframe of name matches.
#' 
#' @param match_df A dataframe of name matches.
#' 
#' @return A dataframe of name matches, with all multiple matches resolved and
#'   anything remaining with more than one match removed.
#'   
resolve_multiple_matches_auto <- function(match_df) {
  match_counts <- count(match_df, original_name)
  
  single_matches <- 
    match_df %>%
    inner_join(
      match_counts %>% filter(n == 1) %>% select(-n),
      by="original_name"
    )
  
  multi_matches <- 
    match_df %>%
    inner_join(
      match_counts %>% filter(n > 1) %>% select(-n),
      by="original_name"
    )
  
  resolved <-
    multi_matches %>%
    group_by(original_name) %>%
    group_modify(~resolve_multi_(.x, .y$original_name)) %>%
    ungroup() %>%
    add_count(original_name) %>%
    filter(n == 1) %>%
    select(-n)
  
  single_matches %>%
    bind_rows(resolved)
}