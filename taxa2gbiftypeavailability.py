import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from unidecode import unidecode
import re
from pygbif import registry
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_tax", type=str)
    parser.add_argument('--delimiter_tax', type=str, default='\t')
    parser.add_argument("inputfile_occ", type=str)
    parser.add_argument('--delimiter_occ', type=str, default='\t')
    parser.add_argument('--year_min', type=int, default=None)
    parser.add_argument("outputfile_data", type=str)
    parser.add_argument("outputfile_yaml", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read input files
    ###########################################################################
    #
    # 1.1 Taxonomy (WCVP and GBIF integrated) =================================
    df_tax = pd.read_csv(args.inputfile_tax, sep=args.delimiter_tax, nrows=args.limit, usecols=['original_id','accepted_id','first_published_yr'])
    print('Read {} taxonomy lines from: {}'.format(len(df_tax), args.inputfile_tax))

    # 1.2 Occurrences from GBIF with type status set ==========================
    df_occ = pd.read_csv(args.inputfile_occ, sep=args.delimiter_occ, nrows=args.limit)
    print('Read {} type occurrence GBIF lines from: {}'.format(len(df_occ), args.inputfile_occ))

    # 1.3 Drop those with typestatus "NOTATYPE"
    dropmask = df_occ.typeStatus.isin(['NOTATYPE'])
    df_occ.drop(df_occ[dropmask].index,inplace=True)
    print('Dropped occurrences flagged NOTATYPE, retained {} lines'.format(len(df_occ)))

    # 1.4 Drop those outside specified date range
    if args.year_min is not None:
        # Occurrences
        dropmask = df_occ.year.notnull() & (df_occ.year < args.year_min)
        df_occ.drop(df_occ[dropmask].index,inplace=True)
        print('Dropped occurrences outside date range ({}-date), retained {} lines'.format(args.year_min, len(df_occ)))
        # Taxonomy
        dropmask = df_tax.first_published_yr.isnull()
        df_tax.drop(df_tax[dropmask].index,inplace=True)
        dropmask = (df_tax.first_published_yr.astype(int) < args.year_min)
        df_tax.drop(df_tax[dropmask].index,inplace=True)
        print('Dropped taxonomy outside date range ({}-date), retained {} lines'.format(args.year_min, len(df_tax)))

    ###########################################################################
    # 2. Attach integrated taxonomy to GBIF occurrence type data
    ###########################################################################
    df = pd.merge(left=df_tax,
                    right=df_occ,
                    left_on='original_id',
                    right_on='taxonKey',
                    how='left' )

    ###########################################################################
    # 3. Report on number of taxa with occurrences claiming type status in GBIF
    ###########################################################################
    mask = (df.typeStatus.notnull())
    type_status_available_count = df[mask].accepted_id.nunique()
    total_taxa_count = df.accepted_id.nunique()
    analysis_variables = dict()
    analysis_variables['taxon_count'] = total_taxa_count
    analysis_variables['taxa_with_types_available_count'] = type_status_available_count
    analysis_variables['taxa_with_types_available_pc'] = round((type_status_available_count/total_taxa_count)*100)
    output_variables = dict()
    output_variables['taxa2gbiftypeavailability']=analysis_variables
    with open(args.outputfile_yaml, 'w') as f:
        yaml.dump(output_variables, f)

    ###########################################################################
    # 4. Output
    ###########################################################################
    print('Outputting {} rows to {}'.format(len(df), args.outputfile_data))
    df.to_csv(args.outputfile_data,sep='\t',index=False)

if __name__ == '__main__':
    main()