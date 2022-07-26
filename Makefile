wcvp_name_url=https://www.dropbox.com/s/pkpv3tc5v9k0thh/wcvp_names.txt?dl=0
gbif_taxonomy_url=#TODO

python_launch_cmd=python
python_launch_cmd=winpty python

date_formatted=$(shell date +%Y%m%d-%H%M%S)

# limit_args can be used in any step that reads a data file (ie explode and link) 
# It will reduce the number of records processed, to ensure a quick sanity check of the process
limit_args= --limit=20000
limit_args=

downloads/wcvp.txt:
	mkdir -p downloads
	wget -O $@ $(wcvp_name_url)
getwcvp: downloads/wcvp.txt

downloads/gbif-taxonomy.zip:
	mkdir -p downloads
	wget -O $@ $(gbif_taxonomy_url)
getgbif: downloads/gbif-taxonomy.zip

data/gbif2wcvp.csv: gbif2wcvp.py downloads/gbif.txt downloads/wcvp.txt
	mkdir -p data
	$(python_launch_cmd) $^ $(limit_args) $@