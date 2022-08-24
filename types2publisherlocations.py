import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from pygbif import registry

GEONAMES_COLUMNS=['geonameid'
                ,'name'
                ,'asciiname'
                ,'alternatenames'
                ,'latitude'
                ,'longitude'
                ,'feature class'
                ,'feature code'
                ,'country code'
                ,'cc2'
                ,'admin1 code'
                ,'admin2 code'
                ,'admin3 code'
                ,'admin4 code'
                ,'population'
                ,'elevation'
                ,'dem'
                ,'timezone'
                ,'modification date']

def getOrganizationData(key):
    organization_data = None
    try:
        organization_data = registry.organizations(data='all', uuid=key)['data']
    except:
        pass
    return organization_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile_gbif", type=str)
    parser.add_argument('--delimiter_gbif', type=str, default='\t')
    parser.add_argument("inputfile_ih", type=str)
    parser.add_argument('--delimiter_ih', type=str, default=',')
    parser.add_argument("inputfile_geonames", type=str)
    parser.add_argument('--delimiter_geonames', type=str, default='\t')

    parser.add_argument("outputfile", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read input files
    ###########################################################################
    #
    # 1.1 Read GBIF data file ===========================================================
    df = pd.read_csv(args.inputfile_gbif, sep=args.delimiter_gbif, nrows=args.limit, usecols=['publishingOrgKey'])
    print('Read {} GBIF lines from: {}'.format(len(df), args.inputfile_gbif))

    # 1.2 Read IH data file ===========================================================
    df_ih = pd.read_csv(args.inputfile_ih, sep=args.delimiter_ih, nrows=args.limit,error_bad_lines=False)
    print('Read {} IH lines from: {}'.format(len(df_ih), args.inputfile_ih))

    # 1.3 Read geonames data file ===========================================================
    df_gn = pd.read_csv(args.inputfile_geonames, sep=args.delimiter_geonames, nrows=args.limit,error_bad_lines=False, names=GEONAMES_COLUMNS)
    print('Read {} geonames lines from: {}'.format(len(df_gn), args.inputfile_geonames))
    df_gn.drop(df_gn[df_gn['feature code']!='PPLC'].index,inplace=True)
    print('Retained {} geonames capital city lines'.format(len(df_gn)))

    ###########################################################################
    # 2. Process publishingOrgKey and join
    ###########################################################################
    # Pass all publishingOrgKey values to get organization metadata from registry
    metadata = {key: getOrganizationData(key) for key in df.publishingOrgKey.unique()}
    # Make a dataframe with the data from the registry
    dfm=pd.DataFrame.from_dict(metadata).T
    # Join to original occurrence oriented dataframe    
    df = pd.merge(left=df
                ,right=dfm[['key','title','latitude','longitude','city','province','country']]
                ,left_on='publishingOrgKey'
                ,right_on='key'
                ,how='left'
                ,suffixes=['','_org'])

    ###########################################################################
    # 3. Fill any gaps (those without lat/long in the GBIF registry) 
    ###########################################################################
    #
    # 3.1 Using IH - first on title, then on city =============================
    for (local_column, ih_column) in {'title':'organization','city':'physicalCity'}.items():
        df = mapLocation(df, local_column, df_ih, ih_column)
    #
    # 3.2 Using geonames to get lat/long of capital city of country============
    df = mapLocation(df, 'country', df_gn, 'country code')

    ###########################################################################
    # 4. Output
    ###########################################################################
    print('Outputting {} rows to {}'.format(len(df), args.outputfile))
    df.to_csv(args.outputfile,sep='\t',index=False)

def mapLocation(df, local_column, df_lookup, lookup_column, lat_column='latitude', long_column='longitude'):
    location_mapper = dict()
    # Establish a mask to find records with no lat/long
    coordinates_missing_mask=df.latitude.isnull()&df.longitude.isnull()
    # Loop over records with missing lat/long, try to find matches in IH on link_column:
    for local_value in df[coordinates_missing_mask][local_column].unique():
        mask = (df_lookup[lookup_column]==local_value)
        if len(df_lookup[mask]) > 0:
            # Save in mapper data structure
            location_mapper[local_value] = (df_lookup[mask].head(n=1)[lat_column].iloc[0],df_lookup[mask].head(n=1)[long_column].iloc[0])
    # Map IH derived lat/long data to temporary column
    df.loc[coordinates_missing_mask,'location_temp']=df[coordinates_missing_mask][local_column].map(location_mapper)
    # Read values from temp column into permanent lat/long home
    coordinates_missing_mask = df.location_temp.notnull()
    df.loc[coordinates_missing_mask,'latitude']=df[coordinates_missing_mask].location_temp.apply(lambda x: x[0])
    df.loc[coordinates_missing_mask,'longitude']=df[coordinates_missing_mask].location_temp.apply(lambda x: x[1])
    # Drop temporary column
    df.drop(columns=['location_temp'],inplace=True)
    return df

if __name__ == '__main__':
    main()