wcvp_name_url=https://www.dropbox.com/s/pkpv3tc5v9k0thh/wcvp_names.txt?dl=0
gbif_taxonomy_url=https://hosted-datasets.gbif.org/datasets/backbone/current/backbone.zip

python_launch_cmd=python
python_launch_cmd=winpty python

date_formatted=$(shell date +%Y%m%d-%H%M%S)

# limit_args can be used in any step that reads a data file (ie explode and link) 
# It will reduce the number of records processed, to ensure a quick sanity check of the process
#limit_args= --limit=100000
#limit_args=

downloads/wcvp.txt:
	mkdir -p downloads
	wget -O $@ $(wcvp_name_url)
getwcvp: downloads/wcvp.txt

downloads/gbif-taxonomy.zip:
	mkdir -p downloads
	wget -O $@ $(gbif_taxonomy_url)
getgbif: downloads/gbif-taxonomy.zip

dl: downloads/wcvp.txt downloads/gbif-taxonomy.zip

data/Taxon.tsv: downloads/gbif-taxonomy.zip
	mkdir -p data
	unzip -d data -uj  downloads/gbif-taxonomy.zip backbone/Taxon.tsv
	# Extracted file will have original mod date - so touch to update
	touch data/Taxon.tsv

data/Taxon-Tracheophyta.tsv: filtergbif.py data/Taxon.tsv
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) --removeHybrids $@
filter: data/Taxon-Tracheophyta.tsv

data/gbif2wcvp.csv: gbif2wcvp.py data/Taxon-Tracheophyta.tsv downloads/wcvp.txt
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) $@

all: data/gbif2wcvp.csv

clean:
	rm -rf data

sterilise:
	rm -rf data
	rm -rf downloads