import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from unidecode import unidecode

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_gbif", type=str)
    parser.add_argument('--delimiter_gbif', type=str, default='\t')
    parser.add_argument("inputfile_wcvp", type=str)
    parser.add_argument('--delimiter_wcvp', type=str, default='|')
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

    ###########################################################################
    # 2. Read WCVP input file and process
    ###########################################################################
    #
    # 2.1 Read file ===========================================================
    df_wcvp = pd.read_csv(args.inputfile_wcvp, sep=args.delimiter_wcvp, nrows=args.limit)
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

    ###########################################################################
    # 3. Match names
    ###########################################################################

    # 3.1 Matching INCLUDING author strings ===================================
    df_match = matchNamesExactly(df_gbif.rename(columns={'scientificName':'taxon_name'})
                                , df_wcvp.rename(columns={'taxon_name_plus_authors':'taxon_name'})
                                , id_col='taxonID'
                                , name_col='taxon_name'
                                , match_cols=['family','genus','taxon_name'])    
    num_ids_matched_stage_1 = df_match[df_match.match_id.notnull()].original_id.nunique()
    print('Number of IDs matched at stage 1: ', num_ids_matched_stage_1)
    gbif_match_1 = pd.merge(left=df_match[df_match.match_id.notnull()]
                            , right=df_gbif[['taxonID','scientificName']].rename(columns={'scientificName':'original_name'})
                            , left_on='original_id'
                            , right_on='taxonID'
                            , how='left')

    # 3.2 Matching EXCLUDING author strings ===================================
    mask = (df_gbif.scientificName.isin(df_match[df_match.match_id.notnull()].match_name)==False)
    df_match = matchNamesExactly(df_gbif[mask].rename(columns={'name':'taxon_name'})
                                , df_wcvp.rename(columns={'taxon_name_minus_authors':'taxon_name'})
                                , id_col='taxonID'
                                , name_col='taxon_name'
                                , match_cols=['taxon_name'])    
    num_ids_matched_stage_2 = df_match[df_match.match_id.notnull()].original_id.nunique()
    print('Number of IDs matched at stage 2: ', num_ids_matched_stage_2)
    gbif_match_2 = pd.merge(left=df_match[df_match.match_id.notnull()]
                            , right=df_gbif[['taxonID','name']].rename(columns={'name':'original_name'})
                            , left_on='original_id'
                            , right_on='taxonID'
                            , how='left')

    # 3.3 Calculate total left unmatched ======================================
    num_unmatched = df_gbif.taxonID.nunique() - num_ids_matched_stage_1 - num_ids_matched_stage_2
    print('Number unmatched:', num_unmatched)

    ###########################################################################
    # 4. Resolve names
    ###########################################################################
    # TODO

    ###########################################################################
    # 5. Output file
    ###########################################################################
    # TODO

def matchNamesExactly(df, df_wcvp, id_col='id', name_col='name', match_cols=['taxon_name']):
    column_mapper_source={id_col:'original_id',
                    name_col:'match_name',
                    'plant_name_id':'match_id',
                    'taxon_rank':'match_rank',
                    'taxon_authors':'match_authors',
                    'taxon_status':'match_status',
                    'accepted_plant_name_id':'accepted_id'}
    df_join = pd.merge(left=df
                        ,right=df_wcvp
                        ,left_on=match_cols
                        ,right_on=match_cols
                        ,how='left')
    df_join.rename(columns=column_mapper_source,inplace=True)
    column_mapper_wcvp = {'plant_name_id':'plant_name_id',
                    'accepted_name':'taxon_name',
                    'accepted_authors':'taxon_authors',
                    'accepted_rank':'taxon_rank'}
    df_join = pd.merge(left=df_join[list(column_mapper_source.values())] 
                    ,right=df_wcvp.rename(columns=column_mapper_wcvp)[[col for col in column_mapper_wcvp.values()]]
                    ,left_on='accepted_id'
                    ,right_on='plant_name_id'
                    ,how='left')

    # Print match statistics
    printMatchStatistics(df_join)

    # Return complete join datastructure
    return df_join

def matchNamesExactly_(df, df_wcvp, id_col='id', name_col='name',match_rank=None,with_author=True):
    if match_rank is not None:
        drop_mask = (df_wcvp.taxon_rank != match_rank)
        df_wcvp.drop(df_wcvp[drop_mask].index,inplace=True)
        print('Retained {} WCVP rows'.format(len(df_wcvp)))
    column_renames={id_col:'original_id',
                    name_col:'match_name',
                    'plant_name_id':'match_id',
                    'taxon_rank':'match_rank',
                    'taxon_authors':'match_authors',
                    'taxon_status':'match_status',
                    'accepted_plant_name_id':'accepted_id'}
    output_cols = column_renames.keys()
    # equiv to "setNames" part of R
    print('Setting taxon_name from ', name_col)
    df['taxon_name']=df[name_col]
    # Use all column names in common for left_join:
    join_cols = [col for col in df_wcvp.columns if col in df.columns]
    print('LEFT joining on: {}'.format(','.join(join_cols)))
    #print(df[join_cols].sample(n=10))
    #print(df_wcvp[join_cols].sample(n=10))
    df_join = pd.merge(left=df,right=df_wcvp,left_on=join_cols,right_on=join_cols,how='left')
    df_join.rename(columns=column_renames,inplace=True)
    #print(df_join[df_join.match_id.notnull()].sample(n=1).T)
    print(list(column_renames.values()))
    #print(df_join.columns)
    print(df_join[list(column_renames.values())])
    wcvp_renames = {'plant_name_id':'plant_name_id',
                    'accepted_name':'taxon_name',
                    'accepted_authors':'taxon_authors',
                    'accepted_rank':'taxon_rank'}
    df_wcvp.rename(columns=wcvp_renames,inplace=True)
    df_join = pd.merge(left=df_join[list(column_renames.values())]
                    ,right=df_wcvp[[col for col in df_wcvp.columns if col in wcvp_renames.values()]]
                    ,left_on='accepted_id'
                    ,right_on='plant_name_id'
                    ,how='left')
    #print(df_join[df_join.match_id.notnull()].sample(n=1).T)


    # Print match statistics
    printMatchStatistics(df_join)

    return df_join[df_join.match_id.notnull()]

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

def resolveAccepted():
    pass

def resolveMulti():
    pass


if __name__ == '__main__':
    main()