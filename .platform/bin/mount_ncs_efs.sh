#!/bin/bash
set -euo pipefail

GET_CONFIG_BIN="/opt/elasticbeanstalk/bin/get-config"
DEFAULT_MOUNT_POINT="/mnt/mirrai-ncs-pdfs"

read_env() {
  local key="$1"
  local value=""

  if [ -n "${!key:-}" ]; then
    printf '%s' "${!key}"
    return 0
  fi

  if [ -x "${GET_CONFIG_BIN}" ]; then
    value="$("${GET_CONFIG_BIN}" environment -k "${key}" 2>/dev/null || true)"
    if [ -n "${value}" ] && [ "${value}" != "null" ]; then
      printf '%s' "${value}"
      return 0
    fi
  fi

  return 1
}

append_fstab_entry() {
  local entry="$1"
  local mount_point="$2"

  if grep -qs "[[:space:]]${mount_point}[[:space:]]" /etc/fstab; then
    return 0
  fi

  printf '%s\n' "${entry}" >> /etc/fstab
}

EFS_FILE_SYSTEM_ID="$(read_env NCS_EFS_FILE_SYSTEM_ID || true)"
EFS_ACCESS_POINT_ID="$(read_env NCS_EFS_ACCESS_POINT_ID || true)"
EFS_REGION="$(read_env NCS_EFS_REGION || read_env AWS_REGION || read_env AWS_DEFAULT_REGION || true)"
EFS_MOUNT_POINT="$(read_env NCS_EFS_MOUNT_POINT || read_env NCS_PDF_SYNC_SOURCE_DIR || true)"

if [ -z "${EFS_MOUNT_POINT}" ]; then
  EFS_MOUNT_POINT="${DEFAULT_MOUNT_POINT}"
fi

if [ -z "${EFS_FILE_SYSTEM_ID}" ]; then
  echo "[eb-ncs-efs] NCS_EFS_FILE_SYSTEM_ID not set; skipping EFS mount."
  exit 0
fi

if [ -z "${EFS_REGION}" ]; then
  echo "[eb-ncs-efs] NCS_EFS_REGION or AWS_REGION is required when NCS_EFS_FILE_SYSTEM_ID is set."
  exit 1
fi

mkdir -p "${EFS_MOUNT_POINT}"

if mountpoint -q "${EFS_MOUNT_POINT}"; then
  echo "[eb-ncs-efs] ${EFS_MOUNT_POINT} is already mounted."
  exit 0
fi

if [ -n "${EFS_ACCESS_POINT_ID}" ] && ! command -v mount.efs >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y amazon-efs-utils
  elif command -v yum >/dev/null 2>&1; then
    yum install -y amazon-efs-utils
  else
    echo "[eb-ncs-efs] amazon-efs-utils is required for access point mounts."
    exit 1
  fi
fi

if command -v mount.efs >/dev/null 2>&1; then
  EFS_OPTIONS="tls,_netdev"
  if [ -n "${EFS_ACCESS_POINT_ID}" ]; then
    EFS_OPTIONS="${EFS_OPTIONS},accesspoint=${EFS_ACCESS_POINT_ID}"
  fi

  append_fstab_entry \
    "${EFS_FILE_SYSTEM_ID}:/ ${EFS_MOUNT_POINT} efs ${EFS_OPTIONS} 0 0" \
    "${EFS_MOUNT_POINT}"

  mount -t efs -o "${EFS_OPTIONS}" "${EFS_FILE_SYSTEM_ID}:/" "${EFS_MOUNT_POINT}"
else
  if [ -n "${EFS_ACCESS_POINT_ID}" ]; then
    echo "[eb-ncs-efs] NCS_EFS_ACCESS_POINT_ID requires amazon-efs-utils on the host."
    exit 1
  fi

  NFS_SOURCE="${EFS_FILE_SYSTEM_ID}.efs.${EFS_REGION}.amazonaws.com:/"
  NFS_OPTIONS="nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noresvport,_netdev"

  append_fstab_entry \
    "${NFS_SOURCE} ${EFS_MOUNT_POINT} nfs4 ${NFS_OPTIONS} 0 0" \
    "${EFS_MOUNT_POINT}"

  mount -t nfs4 -o "${NFS_OPTIONS}" "${NFS_SOURCE}" "${EFS_MOUNT_POINT}"
fi

chmod 0775 "${EFS_MOUNT_POINT}" || true
echo "[eb-ncs-efs] Mounted ${EFS_FILE_SYSTEM_ID} to ${EFS_MOUNT_POINT}."
