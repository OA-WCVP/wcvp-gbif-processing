import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from unidecode import unidecode
import re
from pygbif import registry

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_tax", type=str)
    parser.add_argument('--delimiter_tax', type=str, default='\t')
    parser.add_argument("inputfile_dist", type=str)
    parser.add_argument('--delimiter_dist', type=str, default='|')
    parser.add_argument("inputfile_occ", type=str)
    parser.add_argument('--delimiter_occ', type=str, default='\t')
    parser.add_argument("inputfile_publ", type=str)
    parser.add_argument('--delimiter_publ', type=str, default='\t')
    parser.add_argument("inputfile_tdwg_wgsrpd_l3_json", type=str)
    parser.add_argument("outputfile_data", type=str)
    parser.add_argument("outputfile_md", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read input files
    ###########################################################################
    #
    # 1.1 Taxonomy (WCVP and GBIF integrated) =================================
    df_tax = pd.read_csv(args.inputfile_tax, sep=args.delimiter_tax, nrows=args.limit)
    print('Read {} taxonomy lines from: {}'.format(len(df_tax), args.inputfile_tax))

    # 1.2 WCVP distributions ==================================================
    df_dist = pd.read_csv(args.inputfile_dist, sep=args.delimiter_dist, nrows=args.limit)
    print('Read {} WCVP distributions lines from: {}'.format(len(df_dist), args.inputfile_dist))

    # 1.3 Occurrences from GBIF with type status set ==========================
    df_occ = pd.read_csv(args.inputfile_occ, sep=args.delimiter_occ, nrows=args.limit, usecols=['gbifID','typeStatus','taxonKey','publishingOrgKey'])
    print('Read {} type occurrence GBIF lines from: {}'.format(len(df_occ), args.inputfile_occ))
    # 1.3.1 Drop GBIF occurrences with typestatus "NOTATYPE" ===============================
    dropmask = df_occ.typeStatus.isin(['NOTATYPE'])
    df_occ.drop(df_occ[dropmask].index,inplace=True)
    print('Retained {} type occurrence GBIF lines'.format(len(df_occ)))

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
    df = pd.merge(left=df_tax,
                    right=df_occ,
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
    
    # 3.3 Attach native distributions =========================================
    df = pd.merge(left=df,
                    right=df_dist[df_dist.introduced==0],
                    left_on='accepted_id',
                    right_on='plant_name_id',
                    how='left' )
        
    ###########################################################################
    # 4. Count number of taxa with type material served from within native range
    ###########################################################################
    mask=(df.area_code_l3 == df.LEVEL3_COD)
    accepted_id_served_from_within_native_range_count = df[mask].accepted_id.nunique()
    accepted_id_count = df.accepted_id.nunique()
    summary_message=('{:.2%} taxa ({} of {}) are represented by type material served from within their native range'.format(accepted_id_served_from_within_native_range_count/accepted_id_count, accepted_id_served_from_within_native_range_count, accepted_id_count))

    # ###########################################################################
    # # 4. Output
    # ###########################################################################
    #
    # 4.1 markdown format statement
    with open(args.outputfile_md, 'w') as f:
        print(summary_message)
        f.write(summary_message)
        
    # 4.2 Data
    # TBC
    # print('Outputting {} rows to {}'.format(len(df), args.outputfile_data))
    # df.to_csv(args.outputfile_data,sep='\t',index=False)

if __name__ == '__main__':
    main()