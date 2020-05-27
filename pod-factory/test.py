#!/usr/bin/env python2

import yaml
import logging
import os

#nodeSelector = raw_input("please choose a node you want to bind: ")
#
#with open('pp.yaml', 'r') as f:
#    config = yaml.load(f, Loader=yaml.FullLoader)
#    
#config['spec']['template']['spec']['nodeSelector']['disktype'] = nodeSelector
#
#with open('pp.yaml', 'w') as fname:
#    yaml_string = yaml.dump(config)
#    fname.write(yaml_string)

#with open('pod-pod.yaml') as f:
#    docs = yaml.load_all(f, Loader=yaml.FullLoader)
#    for doc in docs:
#        for k, v in doc.items():
#            print(k, "->", v)
def generate_yaml_doc(yaml_file):
    deploymentName = raw_input("please input the name of deployment you want create(pod-testing): ")
    if deploymentName == "":
        deploymentName = "pod-testing"
    py_object = {
                'apiVersion':'apps/v1',
                'kind':'Deployment',
                'metadata':{'name':deploymentName,'namespace':'ai'}}
    file = open(yaml_file, 'w')
    yaml.dump(py_object, file)
    file.close()


if __name__ == '__main__':
    try:
        current_path = os.path.abspath(".")
        yaml_path = os.path.join(current_path, "generate.yaml")
        generate_yaml_doc(yaml_path)
        logging.info("Created deployments/service/pvc in ai namespaces.")
    except IOError as e:
        logging.error("Failed to create deployments/service/pvc in ai namespaces: {}".format(e))
