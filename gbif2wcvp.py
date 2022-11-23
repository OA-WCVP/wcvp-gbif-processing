import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from unidecode import unidecode
import re
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_gbif", type=str)
    parser.add_argument('--delimiter_gbif', type=str, default='\t')
    parser.add_argument("inputfile_wcvp", type=str)
    parser.add_argument('--delimiter_wcvp', type=str, default='|')
    parser.add_argument("--filter", action='store_true')
    parser.add_argument('--filter_name_prefix', type=str, default='Roella retic')
    
    parser.add_argument("outputfile", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read GBIF input file and process
    ###########################################################################
    #
    # 1.1 Read file ===========================================================
    df_gbif = pd.read_csv(args.inputfile_gbif, sep=args.delimiter_gbif, nrows=args.limit)
    print('Read {} GBIF lines from: {}'.format(len(df_gbif), args.inputfile_gbif))
    #
    # 1.2 Create name column for matching =====================================
    df_gbif['name'] = df_gbif.apply(lambda row: unidecode('{} {}'.format(row['genericName'],row['specificEpithet'])),axis=1)
    # (Note - did look at using the canonicalName column for this purpose BUT whilst it 
    # is mostly OK, a few thousand records (primarily from dataset ID 
    # 7ddf754f-d193-4cc9-b351-99906754a03b) include names of the form "Genus species publnote" 
    # where publnote is one of: cited, made, oppr, publ, ref, validly)
    # These can be retrieved as follows: df[(df_gbif.name != df_gbif.canonicalName)]

    if args.filter:
        dropmask = (df_gbif.scientificName.str.startswith(args.filter_name_prefix)==False)
        df_gbif.drop(df_gbif[dropmask].index,inplace=True)
        print(df_gbif.T)

    ###########################################################################
    # 2. Read WCVP input file and process
    ###########################################################################
    #
    # 2.1 Read file ===========================================================
    df_wcvp = pd.read_csv(args.inputfile_wcvp, sep=args.delimiter_wcvp, nrows=args.limit)
    df_wcvp = df_wcvp.replace({np.nan:None})
    print('Read {} WCVP lines from: {}'.format(len(df_wcvp), args.inputfile_wcvp))
    #
    # 2.2 Process homotypic synonym status ====================================
    mask = (df_wcvp.homotypic_synonym.notnull())
    df_wcvp.loc[mask,'taxon_status'] = 'Homotypic Synonym'
    #
    # 2.3 Add column with name plus/ minus authors ============================
    df_wcvp['taxon_name_plus_authors'] = df_wcvp.apply(lambda row: '{} {}'.format(row['taxon_name'],row['taxon_authors']), axis=1)
    df_wcvp['taxon_name_minus_authors'] = df_wcvp['taxon_name']
    df_wcvp.drop(columns=['taxon_name'],inplace=True)
    #
    # 2.4 Add genericName column
    df_wcvp['genericName'] = df_wcvp['genus']

    if args.filter:
        dropmask = (df_wcvp.taxon_name_plus_authors.str.startswith(args.filter_name_prefix)==False)
        df_wcvp.drop(df_wcvp[dropmask].index,inplace=True)
        print(df_wcvp.T)
    
    ###########################################################################
    # 3. Match names
    ###########################################################################

    # 3.1 Gather list of homonyms as these will be excluded from some of the looser matching strategies
    dfg = df_gbif.groupby('name').agg({'family':'nunique'})
    print('Found {} homonyms: same name (without authors), different family'.format(len(dfg[dfg.family>1])))
    homonym_ids = df_gbif[df_gbif.name.isin(dfg[dfg.family>1].index)].taxonID
    print('Homonyms translate to {} source records'.format(len(homonym_ids)))
    #
    # 3.2 Process a sequence of match strategies, first strict, later looser
    df_matches = None
    match_configurations = [{'gbif_name_source':'scientificName','wcvp_name_source':'taxon_name_plus_authors','match_cols':['family','genericName'],'exclude_homonyms':False},
                            {'gbif_name_source':'scientificName','wcvp_name_source':'taxon_name_plus_authors','match_cols':['genericName'],'exclude_homonyms':False},
                            {'gbif_name_source':'name','wcvp_name_source':'taxon_name_minus_authors','match_cols':['family','genericName'],'exclude_homonyms':True}]

    matched_ids = []
    for i, match_configuration in enumerate(match_configurations):
        # Exclude anything already matched in previous stages
        mask = (df_gbif.taxonID.isin(matched_ids)==False)
        # We may also exclude homonyms from the looser match strategies
        if match_configuration['exclude_homonyms']:
            print('Excluding homonyms')
            mask = mask & (df_gbif.taxonID.isin(homonym_ids)==False)
        # We temporarily apply column renames so that the specified name columns 
        # are both named "match_name" for a simpler pandas join
        gbif_renames = {match_configuration['gbif_name_source']:'match_name'}
        wcvp_renames = {match_configuration['wcvp_name_source']:'match_name'}
        df_match = matchNamesExactly(df_gbif[mask].rename(columns=gbif_renames)
                                , df_wcvp.rename(columns=wcvp_renames)
                                , id_col='taxonID'
                                , name_col='match_name'
                                , match_cols=match_configuration['match_cols'])    
        num_ids_matched = df_match[df_match.match_id.notnull()].original_id.nunique()
        print('Number of IDs matched at stage {}: {}'.format(i, num_ids_matched))
        df_match = pd.merge(left=df_match[df_match.match_id.notnull()]
                                , right=df_gbif[['taxonID','scientificName','name']]
                                , left_on='original_id'
                                , right_on='taxonID'
                                , how='left')
        df_match['original_name'] = df_match[match_configuration['gbif_name_source']]
        # Save match stage for debugging any suspicious matches
        df_match['match_stage'] = [i] * len(df_match)
        df_matches = pd.concat([df_matches,df_match])
        # Update the list of matched IDs so that anything that was matched can be 
        # excluded from later (looser) match strategies
        matched_ids = list(df_matches[df_matches.match_id.notnull()].taxonID.unique())
    #
    # 3.3 Output stats on matches / stage and total left unmatched
    print('Matches by match stage:')
    print(df_matches[df_matches.match_id.notnull()].groupby('match_stage').taxonID.nunique())
    print('Number unmatched = {}'.format(df_gbif.taxonID.nunique() - df_matches[df_matches.match_id.notnull()].taxonID.nunique()))

    ###########################################################################
    # 4. Resolve names - getting data about the accepted name and processing 
    # those which match to multiple names to arrive at a single decision
    ###########################################################################

    df_matches = resolveAccepted(df_matches)
    df_matches = resolveMultipleMatches(df_matches)


    ###########################################################################
    # 5. Add unmatched names
    ###########################################################################

    unmatched_mask = (df_gbif.taxonID.isin(df_matches.taxonID)==False)
    print('Adding unmatched entries from GBIF taxonomy, number of rows:', len(df_gbif[(unmatched_mask)]))
    df_out = pd.concat([df_matches, df_gbif[(unmatched_mask)]])    

    ###########################################################################
    # 6. Add date of publication of name
    ###########################################################################

    print('Adding date of publication of name')
    df_out = pd.merge(left=df_out,right=df_wcvp[['plant_name_id','first_published']],left_on='plant_name_id',right_on='plant_name_id',how='left')
    mask = (df_out.first_published.notnull())
    df_out.loc[mask,'first_published_yr'] = df_out[mask]['first_published'].apply(cleanPublicationYear)

    ###########################################################################
    # 7. Output file
    ###########################################################################
    print('Outputting {} rows to {}'.format(len(df_out), args.outputfile))
    df_out.to_csv(args.outputfile,sep='\t',index=False)

def matchNamesExactly(df, df_wcvp, id_col='id', name_col='name', match_cols=['taxon_name']):
    print('matchNamesExactly: name_col: {}, match_cols: {}'.format(name_col, match_cols))
    column_mapper_source={id_col:'original_id',
                    name_col:'match_name',
                    'plant_name_id':'match_id',
                    'taxon_rank':'match_rank',
                    'taxon_authors':'match_authors',
                    'taxon_status':'match_status',
                    'accepted_plant_name_id':'accepted_id'}
    df_join = pd.merge(left=df
                        ,right=df_wcvp
                        ,left_on=match_cols+[name_col]
                        ,right_on=match_cols+[name_col]
                        ,how='left')
    df_join.rename(columns=column_mapper_source,inplace=True)
    column_mapper_wcvp = {'plant_name_id':'plant_name_id',
                    name_col:'accepted_name',
                    'taxon_authors':'accepted_authors',
                    'taxon_rank':'accepted_rank'}
    df_join = pd.merge(left=df_join[list(column_mapper_source.values())] 
                    ,right=df_wcvp.rename(columns=column_mapper_wcvp)[[col for col in column_mapper_wcvp.values()]]
                    ,left_on='accepted_id'
                    ,right_on='plant_name_id'
                    ,how='left')
    printMatchStatistics(df_join)

    # Return complete join datastructure
    return df_join

def printMatchStatistics(df):
    # Multiple matches
    dfg = df.groupby('original_id').size()
    multiple_match_count  = len(dfg[dfg>1])
    print('Multiple matches: {}'.format(multiple_match_count))
    # Matched names
    matched_name_count = df[df['match_id'].notnull()]['original_id'].nunique()
    print('Matched names: {}'.format(matched_name_count))
    # Unmatched names
    unmatched_name_count = df[df['match_id'].isnull()]['original_id'].nunique()
    print('Unmatched names: {}'.format(unmatched_name_count))

def extractRank(s):
    rank = None
    m = re.search(r'(?<= )(var\.|ssp\.|subsp\.|f.)(?= )',s)
    if m:
        rank = m.groups()[0]
        if rank == 'ssp.':
            rank = 'subsp.'
    return rank

def resolveMultiGroup(dfg):
    matched_row = None
    original_name = dfg['original_name'].unique()[0]
    if len(dfg) == 1:
        matched_row = dfg
    # If the name to match is an infraspecific, take the match with the right rank
    rank = extractRank(original_name)
    if matched_row is None and rank is not None:
        padded_rank = ' {} '.format(rank)
        mask = (dfg.original_name.str.contains(padded_rank))
        if len(dfg[mask]) == 1:
            matched_row = dfg[mask]
    # If there is an accepted name present, take that
    if matched_row is None:
        mask = (dfg.match_status == 'Accepted')
        if len(dfg[mask]) == 1:
            matched_row = dfg[mask]
    # If there is an orthographic variant present, take that
    if matched_row is None:
        mask = (dfg.match_status == 'Orthographic')
        if len(dfg[mask]) == 1:
            matched_row = dfg[mask]
    # If there is a homotypic synonym present, take that
    if matched_row is None:
        mask = (dfg.match_status == 'Homotypic Synonym')
        if len(dfg[mask]) == 1:
            matched_row = dfg[mask]
    return matched_row

def resolveMultipleMatches(df):
    dfg = df.groupby('original_name')['match_id'].nunique().to_frame('match_count')

    df_single = pd.merge(left=df,
                        right=dfg[dfg.match_count==1],
                        left_on='original_name',
                        right_index=True,
                        how='inner').drop(columns='match_count')

    df_multi = pd.merge(left=df,
                        right=dfg[dfg.match_count>1],
                        left_on='original_name',
                        right_index=True,
                        how='inner').drop(columns='match_count')

    # Group df_multi and resolve at group level
    df_multi = df_multi.groupby('original_name').apply(lambda x: resolveMultiGroup(x))
    df_multi.reset_index(drop=True, inplace=True)

    return pd.concat([df_single, df_multi])

def resolveAccepted(df, blank_columns=False):
    # print(df)
    prefix_to_status_mapper={'match':['Accepted'],'accepted':['Homotypic Synonym','Orthographic']}
    dest_prefix = 'accepted_'
    for prefix, statuses in prefix_to_status_mapper.items():
        mask = (df.match_status.isin(statuses))
        for column in ['id','authors','rank','name',]:
            source_column = '{}_{}'.format(prefix,column)
            dest_column = dest_prefix + column
            #print('{}: {}->{}'.format(','.join(statuses), source_column, dest_column))
            df.loc[mask,dest_column]= df[mask][source_column]
    if blank_columns:
        for column in ['id','authors','rank','name',]:
            dest_column = dest_prefix + column
            df.loc[~df.match_status.isin(['Accepted','Homotypic Synonym','Orthographic']),dest_column]= None
    # print(df)
    return df

def cleanPublicationYear(s):
    year = None
    if s is not None:
        s = s.replace('(','').replace(')','')
        if len(s) == len('yyyy'):
            year = s
        elif 'publ. ' in s:
            yearpart = s.split('publ. ',1)[1]
            if len(yearpart) == len('yyyy'):
                year = yearpart
    if year is not None and (re.match(r'^1[7-9][0-9][0-9]$',year) or re.match(r'^20[0-2][0-9]$',year)):
        year = int(year)
    else:
        year = None
    return year

if __name__ == '__main__':
    main()