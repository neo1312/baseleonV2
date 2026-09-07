#!/bin/bash
set -e

ENV="${1:-local}"
PORT_ARG="${2:-all}"
COMMIT_MSG="${3:-deploy}"

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

		# Start db first so healthcheck passes before web starts
		$COMPOSE up -d db

		# Build and start all services (migration runs inside web entrypoint)
		$COMPOSE up --build -d --remove-orphans
		echo "Waiting for containers to come up..."
		echo "Current container status:"
		$COMPOSE ps
		echo "Staging deployment completed"
		;;

	prod)
		# ─── Lista explícita de instancias de ESTE proyecto ─────────────
		# Cada entrada: <puerto>|<carpeta>|<archivo-compose>|<env-file>
		# El script SOLO toca estas. Otros sistemas del VPS no se tocan.
		INSTANCES=(
			"443|.|docker-compose.prod.yml|.env.prod"
			"8087|clone|clone/docker-compose.clone.yml|clone/.env.clone"
		)

		# Seleccionar las instancias a actualizar (local, en orden de la lista)
		SELECTED=()
		for inst in "${INSTANCES[@]}"; do
			port="${inst%%|*}"
			if [ "$PORT_ARG" = "all" ] || [ "$PORT_ARG" = "$port" ]; then
				SELECTED+=("$inst")
			fi
		done

		if [ "${#SELECTED[@]}" -eq 0 ]; then
			echo "ERROR: puerto '$PORT_ARG' no es una instancia de este proyecto."
			echo "Puertos válidos: all, 443, 8087"
			exit 1
		fi

		echo "Starting production deployment (instancias: ${PORT_ARG})..."
		git add .
		git commit -m "$COMMIT_MSG" --allow-empty
		git push

		# Construir el bloque de comandos que se ejecutará en el VPS
		CMDS="set -e
if [ ! -d /app/baseleonV2/.git ]; then
	echo \"No .git found — cloning fresh copy...\"
	rm -rf /app/baseleonV2
	git clone git@github.com:neo1312/baseleonV2.git /app/baseleonV2
fi
cd /app/baseleonV2
git pull
"
		for inst in "${SELECTED[@]}"; do
			port="${inst%%|*}"
			rest="${inst#*|}"
			dir="${rest%%|*}"
			rest2="${rest#*|}"
			compose="${rest2%%|*}"
			envfile="${rest2#*|}"
			CMDS+="echo \">>> Updating instancia puerto $port (compose: $compose)...\"
cd /app/baseleonV2/$dir
docker compose -f \"$compose\" --env-file \"$envfile\" up --build -d --remove-orphans
echo \">>> Estado puerto $port:\"
docker compose -f \"$compose\" ps
"
		done

		ssh root@5.75.162.179 "$CMDS"
		echo "production deployment completed (instancias: ${PORT_ARG})"
		;;
	       *)
		echo "no valido adios"
		exit 1
		;;
esac
