#!/bin/bash
# Script to create a new admin user.
# Prompts for user name, domain and support rights.
# If the domain is viewfinder.co, will prompt for vf passphrase thrice, once when creating the otp,
# another when setting the password, and finally when setting the admin entry.

if [ -z "${VF_HOME}" ]; then
  echo "Missing VF_HOME env variable, exiting.";
  exit
fi

cd ${VF_HOME}
echo -n "Enter new user: "
read user

if [ -z "${user}" ]; then
  echo "Missing user name, exiting.";
  exit
fi 

echo ""
echo "Available domains:"
echo "  1) viewfinder.co"
echo "  2) goviewfinder.com"
echo -n "Enter domain number: "
read domain_id

domain=""
if [ ${domain_id} -eq 1 ]; then
  domain="viewfinder.co"
elif [ ${domain_id} -eq 2 ]; then
  domain="goviewfinder.com"
else
  echo "Invalid domain: \"${domain_id}\", exiting."
  exit
fi

echo ""
echo "Creating OTP for user ${user} in domain ${domain}."
${PYTHON:-python} -m viewfinder.backend.base.otp --devbox --otp_mode=new_secret --domain=${domain} --user=${user}
if [ $? -ne 0 ]; then exit; fi

echo ""
echo "Set password for user ${user} in domain ${domain}."
${PYTHON:-python} -m viewfinder.backend.base.otp --devbox --otp_mode=set_pwd --domain=${domain} --user=${user}
if [ $? -ne 0 ]; then exit; fi

echo ""
echo "User rights:"
echo "  1) root"
echo "  2) support"
echo "  3) root + support"
echo -n "Enter rights: "
read rights_id

rights=""
if [ ${rights_id} -eq 1 ]; then
  rights="root"
elif [ ${rights_id} -eq 2 ]; then
  rights="support"
elif [ ${rights_id} -eq 3 ]; then
  rights="root,support"
else
  echo "Invalid rights: \"${rights_id}\", exiting."
  exit
fi

OPTIONS="--op=set --user=${user} --rights=${rights} --devbox"
if [ ${domain_id} -eq 2 ]; then
  OPTIONS="${OPTIONS} --localdb=True --localdb_dir=${HOME}/local/db -domain=${domain}"
  OPTIONS="${OPTIONS} --host=local.${domain} --fileobjstore=True --fileobjstore_dir=${HOME}/local/fileobjstore"
fi

echo ""
echo "Creating AdminPermissions entry for user ${user} with rights ${rights}."
${PYTHON:-python} -m viewfinder.backend.db.tools.admin_tool ${OPTIONS}
