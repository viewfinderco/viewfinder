#!/bin/bash
# Output the viewfinder certificate and key to stdout. This is the expected contents of the .pem file for haproxy.
# This script takes the secrets passphrase as first argument and the output file as second arg.

domain=$1
if [ -z "${domain}" ];
then
  echo "Invoke as: ./generate_haproxy_certificate.sh <domain> <vf-passphrase> <output-file>"
  exit 1
fi

passphrase=$2
if [ -z "${passphrase}" ];
then
  echo "Invoke as: ./generate_haproxy_certificate.sh <domain> <vf-passphrase> <output-file>"
  exit 1
  exit 1
fi

output=$3
if [ -z "${output}" ];
then
  echo "Invoke as: ./generate_haproxy_certificate.sh <domain> <vf-passphrase> <output-file>"
  exit 1
  exit 1
fi


# We need to grep out the secret's name.
python -m viewfinder.backend.base.secrets_tool \
  --secrets_mode=get_secret \
  --secret=${domain}.crt \
  --passphrase=${passphrase} | \
  egrep -v "^${domain}.crt:$" > ${output}

python -m viewfinder.backend.base.secrets_tool \
  --secrets_mode=get_secret \
  --secret=${domain}.key \
  --passphrase=${passphrase} | \
  egrep -v "^${domain}.key:$" >> ${output}
