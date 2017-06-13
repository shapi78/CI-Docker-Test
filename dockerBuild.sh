#!/bin/bash

if [ -f "docker-compose.yml" ]; then

	echo "Rebuilding Docker Compose"
	sudo docker-compose  up --build --no-deps -d product-service website
else
	echo "Cannot find docker-compose.yml file"
	exit 1
fi
	
