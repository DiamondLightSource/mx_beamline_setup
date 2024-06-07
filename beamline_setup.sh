if [[ $1 == "production" ]]; then
  cd /dls/science/groups/mx/Python/applications/beamline_setup
  elif [[ $1 == "development" ]]; then
  cd /dls/science/groups/i04/Python/applications/beamline_setup
  else
  echo "I don't know what version to use, usage"
  echo "beamline_setup production/development"
  exit
fi
echo ${USER}
if [[ ${USER} == "i04user@dc.diamond.ac.uk" ]]; then
     fedid=$(zenity --entry --text="Type your fedid")
     echo "ssh ${fedid}@i04-ws001.diamond.ac.uk /dls/science/groups/mx/Python/applications/beamline_setup/beamline_setup.sh $1"
     xterm -geometry 200 -title "Beamline Setup LOG" -e "ssh ${fedid}@i04-ws001.diamond.ac.uk /dls/science/groups/mx/Python/applications/beamline_setup/beamline_setup.sh $1"
else
  source /dls/science/groups/i04/setup_i04.sh
  python3 beamline_setup.py
fi
