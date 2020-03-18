#!/usr/bin/env bash
this_dir="$( cd "$( dirname "$0" )" && pwd )"
base_dir="$(realpath "${this_dir}/..")"

lang="$1"
if [[ -z "${lang}" ]]; then
    echo "Usage: run-tests-for.sh <LANGUAGE> [<PROFILE> <PROFILE> ...]"
    exit 1
fi

shift 1

venv="${base_dir}/.venv"
if [[ -d "${venv}" ]]; then
    echo "Using virtual environment at ${venv}"
    source "${venv}/bin/activate"
fi

# -----------------------------------------------------------------------------

# Create a temporary directory for profiles
temp_dir="$(mktemp -d)"

function cleanup {
    rm -rf "${temp_dir}"
}

trap cleanup EXIT

# -----------------------------------------------------------------------------

function wait-for-url() {
    url="$1"
    echo "Waiting for ${url}"
    timeout 30 bash -c \
            'while [[ "$(curl -s -o /dev/null -w "%{http_code}" "${0}")" != "200" ]]; do sleep 0.5; done' \
            "${url}"
}

# -----------------------------------------------------------------------------

profiles_dir="${base_dir}/profiles/${lang}"
shared_dir="${profiles_dir}/shared"

if [[ -z "$1" ]]; then
    # All profiles
    profile_dirs=${profiles_dir}/test_*
else
    # Specific profiles
    profiles=()
    while [[ ! -z "$1" ]]; do
        profiles+=("${profiles_dir}/$1")
        shift 1
    done

    profile_dirs="${profiles[@]}"
fi

for profile_dir in ${profile_dirs}; do
    if [[ ! -d "${profile_dir}" ]]; then
        echo "Directory does not exist: ${profile_dir}"
        exit 1
    fi

    web_port="$(${base_dir}/scripts/get-free-port)"
    mqtt_port="$(${base_dir}/scripts/get-free-port)"
    profile_name="$(basename "${profile_dir}")"
    output_dir="${base_dir}/output/${lang}/${profile_name}"
    rm -rf "${output_dir}"
    mkdir -p "${output_dir}"

    echo "Running ${lang}/${profile_name} (http=${web_port}, mqtt=${mqtt_port})"
    cp -R "${profile_dir}" "${temp_dir}/${lang}"
    cp -R "${shared_dir}"/* "${temp_dir}/${lang}/"

    user="$(id -u):$(id -g)"
    docker_command="docker run -d -v "${temp_dir}:/profiles" --user "${user}" --network host rhasspy/rhasspy:2.5.0-pre --profile "${lang}" --user-profiles /profiles --http-port ${web_port} --local-mqtt-port ${mqtt_port} -- --set download.url_base 'http://localhost:5000'"
    echo "${docker_command}"

    container_id="$(${docker_command})"

    (
        # Block until Rhasspy web server is ready
        wait-for-url "http://localhost:${web_port}/api/version" || exit 1
        echo ''

        # Download all profle artifacts
        echo "Downloading..."
        curl -X POST "http://localhost:${web_port}/api/download-profile" || exit 1
        sleep 1
        echo ''

        # Re-start services
        echo "Restarting..."
        curl -X POST "http://localhost:${web_port}/api/restart" || exit 1
        sleep 1
        echo ''

        # Train profile
        echo "Training..."
        curl -X POST "http://localhost:${web_port}/api/train" || exit 1
        sleep 1
        echo ''

        # Run tests
        echo "Testing..."
        wav_archive="${temp_dir}/${profile_name}.tar.gz"
        (cd "${base_dir}/wav/${lang}" && tar -czf "${wav_archive}" . 2>/dev/null)
        curl -s -X POST -F "archive=@${wav_archive}" "http://localhost:${web_port}/api/evaluate" | \
            tee "${output_dir}/response.txt" | \
            jq . > "${output_dir}/report.json"

        # (cd "${base_dir}" && python3 -m unittest tests/${lang}/*.py) > "${output_dir}/test.txt" || exit 1
        echo 'OK'
    ) || docker stop "${container_id}"

    echo 'Stopping Docker container...'
    docker stop "${container_id}"
    echo "Finished ${profile_name}"
    echo '----------'
    echo ''
done