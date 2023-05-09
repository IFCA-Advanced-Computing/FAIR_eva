FROM ubuntu:22.04

MAINTAINER Fernando Aguilar "aguilarf@ifca.unican.es"

RUN apt-get update -y && \
    apt-get install -y curl python3-pip python3-dev git vim lsof

RUN git clone https://gitlab.ifca.es/ifca-computing/applications/fair_eva.git

WORKDIR /fair_eva

RUN pip3 install -r requirements.txt

EXPOSE 5000 9090
RUN ls
RUN mv /fair_eva/config.ini.template /fair_eva/config.ini
RUN cd /fair_eva
RUN chmod 777 start.sh
RUN cat start.sh
CMD /fair_eva/start.sh
