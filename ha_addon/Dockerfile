FROM ghcr.io/fragnarok/viofosync:ha-app

# HA mounts /config and /recordings owned by root; hand them to the app user.
COPY run.sh /run.sh
RUN sed -i 's/\r$//' /run.sh && chmod +x /run.sh

ENTRYPOINT [ "/run.sh" ]
