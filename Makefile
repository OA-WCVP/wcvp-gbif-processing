wcvp_name_url=https://www.dropbox.com/s/pkpv3tc5v9k0thh/wcvp_names.txt?dl=0
wcvp_dist_url=https://www.dropbox.com/s/9vefyzzp978m2f1/wcvp_distribution.txt?dl=0
gbif_taxonomy_url=https://hosted-datasets.gbif.org/datasets/backbone/current/backbone.zip
tdwg_wgsrpd_l3_url=https://github.com/jiacona/tdwg-geojson/raw/master/tdwg-level3.geojson
ih_url="http://sweetgum.nybg.org/science/api/v1/institutions/search?dateModified=%3E01/01/2000&download=yes"
geonames_capital_cities_url=http://download.geonames.org/export/dump/cities15000.zip

python_launch_cmd=python
python_launch_cmd=winpty python

date_formatted=$(shell date +%Y%m%d-%H%M%S)

username=YOUR_GBIF_USERNAME
password=YOUR_GBIF_PASSWORD

# limit_args can be used in any step that reads a data file (ie explode and link) 
# It will reduce the number of records processed, to ensure a quick sanity check of the process
#limit_args= --limit=100000
#limit_args=

# Download WCVP taxonomy
downloads/wcvp.txt:
	mkdir -p downloads
	wget -O $@ $(wcvp_name_url)
getwcvp: downloads/wcvp.txt

# Download WCVP distributions
downloads/wcvp_dist.txt:
	mkdir -p downloads
	wget -O $@ $(wcvp_dist_url)
getwcvpdist: downloads/wcvp_dist.txt

# Download GBIF taxonomy
downloads/gbif-taxonomy.zip:
	mkdir -p downloads
	wget -O $@ $(gbif_taxonomy_url)
getgbif: downloads/gbif-taxonomy.zip

# Download TDWG WGSRPD L3 as geojson
downloads/tdwg_wgsrpd_l3.json:
	mkdir -p downloads
	wget -O $@ $(tdwg_wgsrpd_l3_url)

# Download IH datafile
downloads/ih.txt:
	mkdir -p downloads
	wget -O $@ $(ih_url)

# Download geonames capital cities
downloads/cities15000.zip:
	mkdir -p downloads	
	wget -O $@ $(geonames_capital_cities_url)

dl: downloads/wcvp.txt downloads/wcvp_dist.txt downloads/gbif-taxonomy.zip downloads/tdwg_wgsrpd_l3.json

# Extract taxon file from GBIF backbone taxonomy
data/Taxon.tsv: downloads/gbif-taxonomy.zip
	mkdir -p data
	unzip -d data -uj  downloads/gbif-taxonomy.zip backbone/Taxon.tsv
	# Extracted file will have original mod date - so touch to update
	touch data/Taxon.tsv

# Filter GBIF backbone taxonomy for Tracheophyta
data/Taxon-Tracheophyta.tsv: filtergbif.py data/Taxon.tsv
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) --removeHybrids $@
filter: data/Taxon-Tracheophyta.tsv

# Process GBIF and WCVP taxonomies
data/gbif2wcvp.csv: gbif2wcvp.py data/Taxon-Tracheophyta.tsv downloads/wcvp.txt
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) $@

# Download GBIF occurrences with type status
data/gbif-type-download.id: resources/gbif-type-specimen-download.json
	curl -s --include --user ${username}:${password} --header "Content-Type: application/json" --data @$^ https://api.gbif.org/v1/occurrence/download/request > $@

getdownloadstatus: data/gbif-type-download.id
	curl -Ss https://api.gbif.org/v1/occurrence/download/$(shell cat $^) | jq .

data/gbif-types.zip: data/gbif-type-download.id
	# Get download ID from file
	$(eval download_id:=$(shell cat $^))
	# Get download link from occurrence download service
	# Will jq throw an error if downloadLink is not found?
	$(eval download_link:=$(shell curl -Ss https://api.gbif.org/v1/occurrence/download/$(download_id) | jq '.downloadLink'))
	# wget it
	wget -O $@ $(download_link)

# Process GBIF type data to add details of publishing organisation
data/gbif-typesloc.zip: types2publisherlocations.py data/gbif-types.zip downloads/ih.txt downloads/cities15000.zip
	$(python_launch_cmd) $^ $(limit_args) $@

# Analyse how many taxa have type material in GBIF
data/taxa2gbiftypeavailability.csv data/taxa2gbiftypeavailability.md: taxa2gbiftypeavailability.py data/gbif2wcvp.csv data/gbif-types.zip
	$(python_launch_cmd) $^ $(limit_args) data/taxa2gbiftypeavailability.csv data/taxa2gbiftypeavailability.md

# Analyse how many taxa have type material published from within native range
data/taxa2nativerangetypeavailability.csv data/taxa2nativerangetypeavailability.md: taxa2nativerangetypeavailability.py data/gbif2wcvp.csv downloads/wcvp_dist.txt data/gbif-types.zip data/gbif-typesloc.zip downloads/tdwg_wgsrpd_l3.json
	$(python_launch_cmd) $^ $(limit_args) data/taxa2nativerangetypeavailability.csv data/taxa2nativerangetypeavailability.md

all: data/taxa2gbiftypeavailability.md data/taxa2nativerangetypeavailability.md

clean:
	rm -rf data

sterilise:
	rm -rf data
	rm -rf downloads
