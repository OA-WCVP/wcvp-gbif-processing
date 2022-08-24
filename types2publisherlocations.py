import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from pygbif import registry

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

    ###########################################################################
    # 2. Process publishingOrgKey and join
    ###########################################################################
    # Pass all publishingOrgKey values to get organization metadata from registry
    metadata = {key: getOrganizationData(key) for key in df.publishingOrgKey.unique()}
    # Make a dataframe with the data from the registry
    dfm=pd.DataFrame.from_dict(metadata).T
    # Join to original occurrence oriented dataframe    
    df = pd.merge(left=df
                ,right=dfm[['key','title','latitude','longitude','country']]
                ,left_on='publishingOrgKey'
                ,right_on='key'
                ,how='left'
                ,suffixes=['','_org'])

    ###########################################################################
    # 3. Fill any gaps (those without lat/long in the GBIF registry) by doing
    # a name lookup to IH
    ###########################################################################
    title_location_mapper = dict()
    # Establish a mask to find records with no lat/long
    coordinates_missing_mask=df.latitude.isnull()&df.longitude.isnull()
    # Loop over records with missing lat/long, try to find matches in IH on title:
    for title in df[coordinates_missing_mask].title.unique():
        mask = (df_ih.organization==title)
        if len(df_ih[mask]) > 0:
            # Save in mapper data structure
            title_location_mapper[title] = (df_ih[mask].head(n=1).latitude.iloc[0],df_ih[mask].head(n=1).longitude.iloc[0])
    # Map IH derived lat/long data to temporary column
    df.loc[coordinates_missing_mask,'location_temp']=df[coordinates_missing_mask].title.map(title_location_mapper)
    # Read values from temp column into permanent lat/long home
    coordinates_missing_mask = df.location_temp.notnull()
    df.loc[coordinates_missing_mask,'latitude']=df[coordinates_missing_mask].location_temp.apply(lambda x: x[0])
    df.loc[coordinates_missing_mask,'longitude']=df[coordinates_missing_mask].location_temp.apply(lambda x: x[1])
    # Drop temporary column
    df.drop(columns=['location_temp'],inplace=True)

    ###########################################################################
    # 4. Output
    ###########################################################################
    print('Outputting {} rows to {}'.format(len(df), args.outputfile))
    df.to_csv(args.outputfile,sep='\t',index=False)

if __name__ == '__main__':
    main()