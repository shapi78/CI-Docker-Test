# CI-Docker-Test
Small CI Demo

This dockerized platform is build on 2 containers - services in docker-compose.

api service - API written in python Flask
webserver service - Apache + PHP which reads JSON from the python API service and displays it

*DockerBuild.sh* - Rebuilds the docker images with docker-compose and runs them

Jenkins was chosen as a CI server.
Jenkins polls this GitHub project, when a commit is detected -  Jenkins rebuilds the docker containers with  *DockerBuilds.sh* script. 
