import pandas as pd
pd.set_option('display.max_rows',100)
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputfile", type=str)
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("--batchsize", default=100000, type=int)
    parser.add_argument('--delimiter', type=str, default='\t')
    parser.add_argument('--phylum', type=str, default='Tracheophyta')
    parser.add_argument('--taxonRank', type=str, default='species')
    parser.add_argument('--removeHybrids', action='store_true')
    parser.add_argument("outputfile", type=str)
    args = parser.parse_args()

    ###########################################################################
    # 1. Assemble filter
    ###########################################################################
    query_filter = "(phylum == '{phylum}') & (taxonRank == '{taxonRank}')".format(phylum=args.phylum, taxonRank=args.taxonRank)

    ###########################################################################
    # 2. Incrementally read file, applying filter
    ###########################################################################
    print('Reading from: {}, filtering on: {}'.format(args.inputfile,query_filter))
    gen = pd.read_csv(args.inputfile, sep=args.delimiter, chunksize=args.batchsize, nrows=args.limit, on_bad_lines='skip')
    df = pd.concat([x.query(query_filter) for x in gen])
    print('Read {} GBIF lines'.format(len(df)))

    ###########################################################################
    # 3. Remove hybrids
    ###########################################################################
    if args.removeHybrids:
        #dropmask = (df.scientificName.str.contains('\u00d7') | df.scientificName.str.contains(' x '))
        dropmask = (df.scientificName.str.contains('\u00d7'))
        df.drop(df[dropmask].index, inplace=True)
        print('Filtered hybrids, retained {} lines'.format(len(df)))

    ###########################################################################
    # 4. Output filtered file
    ###########################################################################
    print('Writing to: {}'.format(args.outputfile))
    df.to_csv(args.outputfile, sep='\t', index=False)

if __name__ == '__main__':
    main()