builtin_interfaces/Time stamp
int8 priority
# Identificador de alerta: 
# 0 = centinela: mensaje sin setear, NO accionable
# 1 = INTRUSO: persona que no se encuentra en la lista de personas autorizadas
int8 ALARM_TYPE_UNKNOWN=0
int8 ALARM_TYPE_INTRUSO=1
int8 alarm_type
string source_node
# determinar si es necesario activar los periféricos de alarma
bool is_emergency