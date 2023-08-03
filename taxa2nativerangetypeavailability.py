import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from unidecode import unidecode
import re
from pygbif import registry
import numpy as np
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_tax", type=str)
    parser.add_argument('--delimiter_tax', type=str, default='\t')
    parser.add_argument("inputfile_dist", type=str)
    parser.add_argument('--delimiter_dist', type=str, default='|')
    parser.add_argument("inputfile_occ", type=str)
    parser.add_argument('--year_min', type=int, default=None)
    parser.add_argument('--delimiter_occ', type=str, default='\t')
    parser.add_argument("inputfile_publ", type=str)
    parser.add_argument('--delimiter_publ', type=str, default='\t')
    parser.add_argument("inputfile_tdwg_wgsrpd_l3_json", type=str)
    parser.add_argument("outputfile_data", type=str)
    parser.add_argument("outputfile_yaml", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read input files
    ###########################################################################
    #
    # 1.1 Taxonomy (WCVP and GBIF integrated) =================================
    df_tax = pd.read_csv(args.inputfile_tax, sep=args.delimiter_tax, nrows=args.limit,usecols=['original_id','accepted_id','first_published_yr'])
    print('Read {} taxonomy lines from: {}'.format(len(df_tax), args.inputfile_tax))
    df_tax = df_tax.replace({np.nan:None})

    # 1.2 WCVP distributions ==================================================
    df_dist = pd.read_csv(args.inputfile_dist, sep=args.delimiter_dist, nrows=args.limit)
    print('Read {} WCVP distributions lines from: {}'.format(len(df_dist), args.inputfile_dist))

    # 1.3 Occurrences from GBIF with type status set ==========================
    df_occ = pd.read_csv(args.inputfile_occ, sep=args.delimiter_occ, nrows=args.limit, usecols=['gbifID','typeStatus','taxonKey','publishingOrgKey','year'])
    print('Read {} type occurrence GBIF lines from: {}'.format(len(df_occ), args.inputfile_occ))
    # 1.3.1 Drop GBIF occurrences with typestatus "NOTATYPE" ===============================
    dropmask = df_occ.typeStatus.isin(['NOTATYPE'])
    df_occ.drop(df_occ[dropmask].index,inplace=True)
    print('Dropped occurrences flagged NOTATYPE, retained {} lines'.format(len(df_occ)))
    # 1.3.2 Drop data outside specified daterange ==============================
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

    # 1.4 Publishing organisation locations (GBIF) ============================
    df_publ = pd.read_csv(args.inputfile_publ, sep=args.delimiter_publ, nrows=args.limit, usecols=['publishingOrgKey','latitude','longitude','country'])
    df_publ.drop_duplicates(inplace=True)
    print('Read {} GBIF publishing organisation lines from: {}'.format(len(df_publ), args.inputfile_publ))

    ###########################################################################    
    # 2 Determine TDWG WGSRPD L3 region from lat/long =========================
    ###########################################################################    
    import geopandas as gpd
    #
    # 2.1 Convert publishing organization locations to points ==================
    df_point = gpd.GeoDataFrame(df_publ[['publishingOrgKey','latitude','longitude']].drop_duplicates(), geometry=gpd.points_from_xy(df_publ['longitude'], df_publ['latitude']))
    print('Number of points requiring assignment to TDWG regions:', len(df_point)
          
    ## 2.2 Read TDWG WGSRPD L3 geojson format shape file ========================
    df_poly = gpd.read_file(args.inputfile_tdwg_wgsrpd_l3_json)
    print('Read {} TDWG WGSRPD l3 shapes from {}'.format(len(df_poly), args.inputfile_tdwg_wgsrpd_l3_json))
    #
    # 2.3 Determine intersection ===============================================
    df_point.crs = df_poly.crs
    df_intersect = df_point.sjoin(df_poly, how="left")

    ###########################################################################
    # 3. Integrate taxonomy (df_tax), occurrences (df_occ) and TDWG WGSRPD L3 
    # (df_intersect) in which the publisher is located
    ###########################################################################
    #
    # 3.1 Attach integrated taxonomy to GBIF occurrence type data==============
    mask=(df_tax['original_id'].notnull())
    df_tax.loc[mask,'original_id']=df_tax[mask]['original_id'].astype(int)
    mask=(df_occ['taxonKey'].notnull())
    df_occ.loc[mask,'taxonKey']=df_occ[mask]['taxonKey'].astype(int)
    df = pd.merge(left=df_tax[df_tax['original_id'].notnull()],
                    right=df_occ[df_occ['taxonKey'].notnull()],
                    left_on='original_id',
                    right_on='taxonKey',
                    how='left' )

    # 3.2 Attach publ org locations and containing TDWG WGSRPD L3 region ======
    df = pd.merge(left=df,
                    right=df_intersect[['publishingOrgKey','latitude','longitude','LEVEL3_COD']],
                    left_on='publishingOrgKey',
                    right_on='publishingOrgKey',
                    how='left',
                    suffixes=['','_org'])
    df.rename(columns={'LEVEL3_COD':'publishingOrg_area_code_l3'},inplace=True)

    # 3.3 Attach native distributions =========================================
    df = pd.merge(left=df,
                    right=df_dist[df_dist.introduced==0],
                    left_on='accepted_id',
                    right_on='plant_name_id',
                    how='left' )
        
    # 3.4 Establish WGSRPD level 2 and level 1 codes from LEVEL3_COD ==========
    for higher_level_code in ['region_code_l2','continent_code_l1']:
        wgsrpd_mapper = df[['area_code_l3',higher_level_code]].drop_duplicates().set_index('area_code_l3')[higher_level_code].to_dict()
        new_col = 'publishingOrg_' + higher_level_code
        df[new_col] = df['publishingOrg_area_code_l3'].map(wgsrpd_mapper)
   
    ###########################################################################
    # 4. Count number of taxa with type material served from within native range
    ###########################################################################
    wgsrpd_columns = {'continent_code_l1':'publishingOrg_continent_code_l1',
                        'region_code_l2':'publishingOrg_region_code_l2',
                        'area_code_l3':'publishingOrg_area_code_l3'}
    analysis_variables = dict()
    accepted_id_count = df.accepted_id.nunique()
    analysis_variables['taxon_count'] = accepted_id_count
    summary_message=""
    for (distribution_loc, publishing_org_loc) in wgsrpd_columns.items():
        mask=(df[distribution_loc] == df[publishing_org_loc])
        accepted_id_served_from_within_native_range_count = df[mask].accepted_id.nunique()
        summary_message += ('- {:.2%} taxa ({} of {}) are represented by type material served from within their native range in {}\n'.format(accepted_id_served_from_within_native_range_count/accepted_id_count, accepted_id_served_from_within_native_range_count, accepted_id_count, distribution_loc))
        current_level_variables = dict()
        current_level_variables['taxon_represented_total']=accepted_id_served_from_within_native_range_count
        current_level_variables['taxon_represented_pc']=round((accepted_id_served_from_within_native_range_count/accepted_id_count)*100)
        analysis_variables[distribution_loc] = current_level_variables
    
    output_variables = dict()
    output_variables['taxa2nativerangetypeavailability'] = analysis_variables

    # ###########################################################################
    # # 4. Output
    # ###########################################################################
    #
    # 4.1 YAML format data variables
    with open(args.outputfile_yaml, 'w') as f:
        yaml.dump(output_variables, f)
        
    # 4.2 Data
    # TBC
    # print('Outputting {} rows to {}'.format(len(df), args.outputfile_data))
    # df.to_csv(args.outputfile_data,sep='\t',index=False)

if __name__ == '__main__':
    main()
