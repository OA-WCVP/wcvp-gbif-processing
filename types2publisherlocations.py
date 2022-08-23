import pandas as pd
pd.set_option('display.max_rows',100)
import argparse
from pygbif import registry

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("inputfile", type=str)
    parser.add_argument('--delimiter', type=str, default='\t')
    parser.add_argument("outputfile", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Read GBIF input file 
    ###########################################################################
    #
    # 1.1 Read file ===========================================================
    df = pd.read_csv(args.inputfile, sep=args.delimiter, nrows=args.limit, usecols=['publishingOrgKey'])
    print('Read {} GBIF lines from: {}'.format(len(df), args.inputfile))

    ###########################################################################
    # 2. Process publishingOrgKey and join
    ###########################################################################
    # Pass all publishingOrgKey values to get organization metadata from registry
    metadata = {key: registry.organizations(data='all', uuid=key)['data'] for key in df.publishingOrgKey.unique()}
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
    # 3. Output
    ###########################################################################
    print('Outputting {} rows to {}'.format(len(df), args.outputfile))
    df.to_csv(args.outputfile,sep='\t',index=False)

if __name__ == '__main__':
    main()