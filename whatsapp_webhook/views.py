from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from ordenes.models import Cliente, OrdenTrabajo
from twilio.twiml.messaging_response import MessagingResponse
from ordenes.models import SystemState

# --- MENÚS DE OPCIONES (Sin cambios) ---

MENU_PRINCIPAL = """
Por favor, selecciona el tipo de problema:
*(Envía solo el número)*

*1.* 💻 Sin Internet
*2.* 📺 Problemas de TV Cable
*3.* 💡 Daño Físico (ej: Fibra cortada, poste caído)
"""

MENU_SOLUCION_INTERNET = """
Entendido. Antes de enviar un técnico, prueba esto:
1. Desenchufa tu router de la corriente.
2. Espera 10 segundos.
3. Vuelve a enchufarlo y espera 2 minutos a que inicien las luces.

---
¿Esto solucionó tu problema?
*(Envía solo el número)*

*1.* Sí, ¡muchas gracias!
*2.* No, sigo sin internet.
*0.* Volver al menú anterior.
"""

MENU_SOLUCION_CABLE = """
Entendido. Antes de enviar un técnico, prueba esto:
1. Asegúrate de que el cable coaxial esté bien apretado en la parte trasera del decodificador y en la pared.
2. Desenchufa tu decodificador de la corriente, espera 10 segundos y vuelve a enchufarlo.

---
¿Esto solucionó tu problema?
*(Envía solo el número)*

*1.* Sí, ¡muchas gracias!
*2.* No, sigo con problemas.
*0.* Volver al menú anterior.
"""

MENU_CONFIRMAR_TECNICO = """
Lamento que el problema persista.
¿Confirmas que necesitas la visita de un técnico en terreno?

*1.* Sí, por favor.
*2.* No, cancelar por ahora.
*0.* Volver al menú anterior.
"""

MENU_DAÑO_FISICO = """
Un daño físico (fibra/cable cortado o poste caído) requiere sí o sí la visita de un técnico.

¿Confirmas que deseas agendar la visita?

*1.* Sí, agendar visita.
*2.* No, cancelar.
*0.* Volver al menú anterior.
"""
# --- FIN DE LOS MENÚS ---


@csrf_exempt
def twilio_webhook(request):
    if request.method == 'POST':
        body = request.POST.get('Body', '')
        sender_phone = request.POST.get('From', '')
        if sender_phone.startswith('whatsapp:'):
            sender_phone = sender_phone[9:]

        response = MessagingResponse()
        
        # --- 2. ¡CHEQUEO DE EMERGENCIA! ---
        # Verificamos el estado ANTES de hacer nada más
        system_state = SystemState.get_state()
        if system_state.is_emergency:
            response.message("🚨 *ALERTA DE SERVICIO (INTERCATV)* 🚨")
            response.message(system_state.emergency_message)
            response.message("\nPor favor, tenga paciencia. Le atenderemos tan pronto se restaure el servicio. No es necesario crear una nueva orden.")
            return HttpResponse(str(response), content_type="application/xml")
        # --- FIN DEL CHEQUEO ---
        
        cliente, created = Cliente.objects.get_or_create(
            telefono=sender_phone,
            defaults={'nombre': f'Cliente {sender_phone}', 'direccion': 'Desconocida', 'chat_state': 'START'}
        )
        
        if body != '0' and cliente.chat_state != 'START':
            cliente.temp_data['previous_state'] = cliente.chat_state
            
        if body == '0':
            if 'REGISTER' in cliente.temp_data.get('previous_state', 'START'):
                previous_state = 'START'
            else:
                previous_state = cliente.temp_data.get('previous_state', 'START')
                
            cliente.chat_state = previous_state
            return handle_state(cliente, response, body='(Volviendo)')

        try:
            return handle_state(cliente, response, body)
        
        except Exception as e:
            print(f"Error fatal en webhook: {e}")
            response.message("Ocurrió un error inesperado. Reiniciando conversación. Envía 'Hola' para empezar.")
            cliente.chat_state = 'START'
            cliente.temp_data = {}
            cliente.save()
            return HttpResponse(str(response), content_type="application/xml")
            
    return HttpResponse("Método no permitido", status=405)


def handle_state(cliente, response, body):
    """
    Maneja la lógica de la máquina de estados.
    """
    
    current_state = cliente.chat_state
    
    # --- ESTADO 1: INICIO Y VERIFICACIÓN DE REGISTRO ---
    if current_state == 'START':
        response.message("¡Hola! Bienvenido al asistente virtual de INTERCATV.")
        
        if cliente.nombre.startswith('Cliente '): 
            response.message("Vemos que eres nuevo por aquí. Para registrarte, por favor indícame tu **Nombre y Apellido**.")
            cliente.chat_state = 'REGISTER_NAME'
        else: 
            response.message(f"Hola {cliente.nombre}, ¡qué gusto verte de nuevo!")
            response.message(MENU_PRINCIPAL)
            cliente.chat_state = 'HANDLE_PROBLEM_CATEGORY'
            
    # --- ESTADO 2: REGISTRO (Pidiendo Nombre) ---
    elif current_state == 'REGISTER_NAME':
        cliente.temp_data['nombre_temp'] = body
        response.message(f"Gracias, {body}. Ahora, por favor, indícame tu **Dirección** (Calle, Número, Sector).")
        cliente.chat_state = 'REGISTER_ADDRESS'

    # --- ESTADO 3: REGISTRO (Pidiendo Dirección y Finalizando) ---
    elif current_state == 'REGISTER_ADDRESS':
        cliente.temp_data['direccion_temp'] = body
        
        cliente.nombre = cliente.temp_data.get('nombre_temp', f'Cliente {cliente.telefono}')
        cliente.direccion = cliente.temp_data.get('direccion_temp', 'Desconocida')
        cliente.temp_data = {} # Limpiamos memoria
        
        response.message("¡Registro completado! Tus datos han sido guardados.")
        response.message(MENU_PRINCIPAL)
        cliente.chat_state = 'HANDLE_PROBLEM_CATEGORY'

    # --- ESTADO 4: MANEJO DE SELECCIÓN DE PROBLEMA ---
    elif current_state == 'HANDLE_PROBLEM_CATEGORY':
        cliente.temp_data['problem_category'] = body 
        
        if body == '1': 
            response.message(MENU_SOLUCION_INTERNET)
            cliente.chat_state = 'HANDLE_TROUBLESHOOTING'
        elif body == '2': 
            response.message(MENU_SOLUCION_CABLE)
            cliente.chat_state = 'HANDLE_TROUBLESHOOTING'
        elif body == '3': 
            response.message(MENU_DAÑO_FISICO)
            cliente.chat_state = 'ASK_TECH_CONFIRM' 
        else:
            response.message("Opción no válida. Por favor, envía solo el número (1, 2, 3 o 0).")
            response.message(MENU_PRINCIPAL)

    # --- ESTADO 5: MANEJO DE TROUBLESHOOTING ---
    elif current_state == 'HANDLE_TROUBLESHOOTING':
        if body == '1': # "Sí, se solucionó"
            response.message("¡Excelente! Nos alegra haberte ayudado. 😊\nSi necesitas algo más, solo envía 'Hola'.")
            cliente.chat_state = 'START' 
            cliente.temp_data = {}
        elif body == '2': # "No, sigo con problemas"
            response.message(MENU_CONFIRMAR_TECNICO)
            cliente.chat_state = 'ASK_TECH_CONFIRM'
        else:
            response.message("Opción no válida. Por favor, responde 1 (Sí), 2 (No) o 0 (Volver).")

    # --- ESTADO 6: CONFIRMAR TÉCNICO (MODIFICADO) ---
    elif current_state == 'ASK_TECH_CONFIRM':
        if body == '1': # "Sí, necesito un técnico"
            # --- ¡AQUÍ ESTÁ EL CAMBIO! ---
            # En lugar de crear la orden, pedimos la descripción final.
            response.message("Entendido. Por favor, **describe brevemente tu problema** o añade cualquier detalle que el técnico deba saber (ej: 'El cable está cortado en el poste', 'La luz del router está roja', etc.).")
            cliente.chat_state = 'CREATE_ORDER_FINAL' # Nuevo estado para crear la orden
            
        elif body == '2': # "No, cancelar"
            response.message("Entendido. Estaremos aquí si nos necesitas. Si el problema vuelve, solo envía 'Hola' para empezar.")
            cliente.chat_state = 'START'
            cliente.temp_data = {}
            
        else:
            response.message("Opción no válida. Por favor, responde 1 (Sí), 2 (No) o 0 (Volver).")

    # --- ESTADO 7: CREAR ORDEN FINAL (NUEVO) ---
    elif current_state == 'CREATE_ORDER_FINAL':
        # El 'body' de este estado es la descripción final del cliente
        final_description = body
        
        try:
            # Determinamos el problema base (de la memoria temporal)
            problem_type = cliente.temp_data.get('problem_category')
            if problem_type == '1': base_desc = "Sin internet"
            elif problem_type == '2': base_desc = "Problemas TV Cable"
            elif problem_type == '3': base_desc = "Daño Físico reportado"
            else: base_desc = "Problema General"

            # Combinamos la descripción
            full_description = f"[{base_desc}] {final_description}"
            
            # Creamos la orden
            nueva_orden = OrdenTrabajo.objects.create(
                cliente=cliente,
                descripcion=full_description, # ¡Usamos la descripción final!
                prioridad='ALTA' if problem_type == '3' else 'MEDIA',
                estado='PENDIENTE',
                ubicacion_servicio=cliente.direccion
            )
            
            response.message(f"¡Orden Creada con Éxito! 🚀\n\n*Su N° de Orden es: {nueva_orden.id}*\n*Cliente:* {cliente.nombre}\n*Dirección:* {cliente.direccion}\n*Problema:* {full_description}\n\nUn administrador revisará su caso a la brevedad.")
            cliente.chat_state = 'START'
            cliente.temp_data = {}

        except Exception as e:
            print(f"Error creando orden: {e}")
            response.message("Hubo un error al crear su orden. Por favor, intente de nuevo más tarde.")
            cliente.chat_state = 'START'

            
    # Estado de fallback
    else:
        response.message("Hubo un error en la conversación, la reiniciaremos. Por favor, envía 'Hola'.")
        cliente.chat_state = 'START'
        cliente.temp_data = {}

    # Guardamos los cambios en el cliente
    cliente.save()
    return HttpResponse(str(response), content_type="application/xml")