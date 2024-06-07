# Config loader
# If changing from yaml to json or pickle function load_config needs changing as well
import yaml as config_loader

import logging
from logging.config import dictConfig

from beamline import ID
from beamline import redis

# import json as serialiser
import pickle as serialiser


class Config(object):
    def __init__(self, reload_config=True, default_name=True, yaml_file="default"):
        # Setup Beamline
        self.ID = ID

        # Setting up loging with default class name or manually set name
        if default_name == True:
            self.log = logging.getLogger(self.__class__.__name__)
        else:
            self.log = logging.getLogger(default_name)

        # Read configuration from file
        if yaml_file == "default":
            config = "configure_blsetup.yaml"
        else:
            config = yaml_file

        self.log.debug(f"Configuration file set to: {config}")

        self.config = self.load_config(config)

        # Giving access to all subclasses to the redis database
        # Setting up redis database
        self.redis_hash = self.config["redis_hash"]["key"].format(BEAMLINE=self.ID)
        self.redis_expiry = self.config["redis_hash"]["expiry"]
        self.names = set(self.config["modules"].keys())
        self.nx_machines = self.config["nx_machines"][self.ID]

        # Load/Not load logging configuration
        if reload_config is not False:
            dictConfig(self.config["logging"])

    def load_config(self, file):
        # Load config. TODO: not totally abstracted from yaml as we need to tell the yaml.loader. If changed to pickle,json code needs changing here
        self.log.debug(f"Loading configuration file from {file}")
        return config_loader.load(open(file, "r"), Loader=config_loader.FullLoader)

    def set(self, key, value):
        redis.hset(self.redis_hash, key, serialiser.dumps(value))
        self.set_redis_expiry()

    def get(self, key):
        try:
            return serialiser.loads(redis.hget(self.redis_hash, key))
        except Exception as e:
            self.log.warning(f"Could not get value for key {key}")
            return False

    def set_redis_expiry(self):
        return redis.expire(self.redis_hash, self.redis_expiry)

    def is_any_module_running(self):
        try:
            status = self.get("module_running")
        except TypeError:
            self.log.debug(
                "redis hash key for checking if modules are running does not exist. creating one as False"
            )
            self.set("module_running", False)

        return self.get("module_running")

    def get_all(self):
        dict_store = {}
        payload = redis.hgetall(self.redis_hash)
        for elem in payload.keys():
            self.log.debug(elem.decode())
            dict_store[elem.decode()] = self.get(elem)
        return dict_store

    def delete_redis_key(self):
        redis.delete(self.redis_hash)
