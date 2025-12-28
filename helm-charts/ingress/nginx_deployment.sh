kubectl create ns nginx-system
helm upgrade --install nginx-ingress ./helm-charts/nginx-ingress -n nginx-system