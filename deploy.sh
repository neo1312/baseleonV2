#!/bin/bash
set -e

ENV="${1:-local}"
COMMIT_MSG="${2:-deploy}"

case $ENV in
	local)
		source env/bin/activate
		python3 manage.py makemigrations
		python3 manage.py migrate
		python3 manage.py runserver 
		;;
	stage)
		echo "Starting staging deployment ..."
		COMPOSE="docker compose -f docker-compose.stage.yml --env-file .env.stage"
		echo "Building and starting containers..."
		$COMPOSE down
		$COMPOSE up --build -d --remove-orphans
		echo "Waiting for containers to come up..."
		echo "Current container status:"
		$COMPOSE ps
		echo "Stage deploment completed"
		;;

	prod)
		echo "Starting production deployment..."
		git add .
		git commit -m "$COMMIT_MSG" --allow-empty
		git push
		ssh root@5.75.162.179 <<-EOF
		cd /app/baseleonV2
		git pull
		docker compose -f docker-compose.prod.yml --env-file .env.prod down
		docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d --remove-orphans
		EOF
		echo "production deploment completed"
		;;
	       *)
		echo "no valido adios"
		exit 1
		;;
esac
