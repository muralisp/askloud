{{/*
Expand the name of the chart.
*/}}
{{- define "askloud-gui.name" -}}
{{- .Chart.Name }}
{{- end }}

{{/*
Create a fully qualified app name using release name + chart name.
Truncated to 63 chars (Kubernetes label limit).
*/}}
{{- define "askloud-gui.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "askloud-gui.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ include "askloud-gui.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "askloud-gui.selectorLabels" -}}
app.kubernetes.io/name: {{ include "askloud-gui.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
