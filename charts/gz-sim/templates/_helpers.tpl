{{- define "gzsim.fullname" -}}
{{- .Release.Name }}-gazebo
{{- end }}

{{- define "gzsim.labels" -}}
app.kubernetes.io/name: gz-sim
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.sim }}
gz-sim/sim: {{ .Values.sim }}
{{- end }}
{{- end }}

{{- define "gzsim.selectorLabels" -}}
app.kubernetes.io/name: gz-sim
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
