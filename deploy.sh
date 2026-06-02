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

		# Pre-flight checks
		if [ ! -f docker-compose.stage.yml ]; then
			echo "ERROR: docker-compose.stage.yml not found"
			exit 1
		fi
		if [ ! -f .env.stage ]; then
			echo "ERROR: .env.stage not found"
			exit 1
		fi

		echo "Building and starting containers..."
		$COMPOSE down

		# Build fresh image first, then run migration with it
		$COMPOSE build web
		# Start db, then run migrations before starting full stack
		$COMPOSE up -d db
		$COMPOSE run --rm web python manage.py migrate --noinput

		$COMPOSE up -d --remove-orphans
		echo "Waiting for containers to come up..."
		echo "Current container status:"
		$COMPOSE ps
		echo "Staging deployment completed"
		;;

	prod)
		echo "Starting production deployment..."
		git add .
		git commit -m "$COMMIT_MSG" --allow-empty
		git push
		ssh root@5.75.162.179 <<-EOF
		set -e
		cd /app
		if [ ! -d /app/baseleonV2/.git ]; then
			echo "No .git found — cloning fresh copy..."
			rm -rf baseleonV2
			git clone git@github.com:neo1312/baseleonV2.git baseleonV2
		fi
		cd /app/baseleonV2
		git pull

		docker compose -f docker-compose.prod.yml --env-file .env.prod down

		# Run migrations BEFORE starting containers to catch errors early
		docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm --no-deps web python manage.py migrate --noinput

		docker compose -f docker-compose.prod.yml --env-file .env.prod up --build -d --remove-orphans
		EOF
		echo "production deployment completed"
		;;
	       *)
		echo "no valido adios"
		exit 1
		;;
esac
