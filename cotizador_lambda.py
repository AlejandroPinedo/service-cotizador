# service-cotizador/cotizador_lambda.py
import json
import os
import boto3
import uuid
# import psycopg2
# import base64 # Necesario si secretsmanager retorna base64
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

# Inicialización de clientes de AWS SDK
s3 = boto3.client('s3')
eventbridge = boto3.client('events')
#secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')
cotizaciones_table = dynamodb.Table(os.environ['COTIZACIONES_TABLE_NAME'])


# Variables de entorno
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
#AURORA_SECRET_ARN = os.environ['AURORA_SECRET_ARN']
EVENT_BUS_NAME = os.environ['EVENT_BUS_NAME']

# Cache de la conexión a la base de datos (para warm starts)
# db_connection_pool = None


# def get_db_connection():
#     """
#     Establece y retorna una conexión a la base de datos Aurora PostgreSQL.
#     Usa el ARN del secreto de Secrets Manager.
#     """
#     global db_connection_pool
#     if db_connection_pool is None:
#         try:
#             secret_value = secrets_client.get_secret_value(SecretId=AURORA_SECRET_ARN)['SecretString']
#             # Algunos secretos de Secrets Manager pueden ser base64 si son binarios, pero para DB suelen ser string JSON
#             try:
#                 secret = json.loads(secret_value)
#             except json.JSONDecodeError:
#                 secret = json.loads(base64.b64decode(secret_value).decode('utf-8')) # En caso de que sea JSON base64
            
#             db_connection_pool = psycopg2.connect(
#                 host=secret['host'],
#                 port=secret['port'],
#                 user=secret['username'],
#                 password=secret['password'],
#                 dbname=secret['dbname'],
#                 # sslmode='require' # Opcional, dependiendo de la configuración de Aurora
#             )
#             print("Conexión a la base de datos establecida y puesta en pool.")
#         except Exception as e:
#             print(f"Error al establecer conexión con la base de datos: {e}")
#             raise e
#     return db_connection_pool


def generate_cotizacion_pdf(cotizacion_data, cotizacion_id):
    """
    Genera un PDF para la cotización con los datos proporcionados.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Simple diseño de PDF - se puede expandir
    c.setFont('Helvetica-Bold', 14)
    c.drawString(100, 750, "COTIZACIÓN DE SERVICIOS")
    c.setFont('Helvetica', 12)
    c.drawString(100, 730, f"No. de Cotización: {cotizacion_id}")
    c.drawString(100, 710, f"Fecha: {cotizacion_data.get('fecha_generacion', '').split('T')[0]}")
    c.drawString(100, 690, f"Cliente ID: {cotizacion_data.get('client_id')}")
    
    c.drawString(100, 650, f"Servicio Solicitado: {cotizacion_data.get('servicio_solicitado')}")
    c.drawString(100, 630, f"Descripción: {cotizacion_data.get('detalles', 'N/A')}")
    
    y_pos = 580
    c.drawString(100, y_pos, "--------------------------------------------------------------------------------")
    y_pos -= 15
    c.drawString(100, y_pos, "ITEM                      CANT.      UNIDAD      PRECIO UNIT.      SUBTOTAL")
    y_pos -= 10
    c.drawString(100, y_pos, "--------------------------------------------------------------------------------")
    y_pos -= 15

    for line in cotizacion_data.get('lineas_cotizacion', []):
        c.drawString(100, y_pos, f"{line.get('descripcion', 'N/A'):<25} {line.get('cantidad', 0):<10.2f} {line.get('unidad', 'N/A'):<10} ${line.get('precio_unitario', 0):<15.2f} ${line.get('subtotal', 0):.2f}")
        y_pos -= 15
    
    y_pos -= 20
    c.drawString(350, y_pos, f"Total Neto: ${cotizacion_data.get('total_neto', 0):,.2f}")

    c.showPage()
    c.save()
    
    buffer.seek(0)
    return buffer


def generate_quote_data(solicitud_data):
    # Lógica simplificada de cotización
    # Aquí se simularía la lógica de cálculo o consulta de tarifas
    
    # 1. Simular búsqueda de servicio y cálculo
    service_cost = 5000 
    margin = 1.2
    
    # 2. Generar datos de cotización
    cotizacion_id = str(uuid.uuid4())
    total_price = service_cost * margin
    
    # Datos de la cotización para guardar en DynamoDB
    cotizacion = {
        'cotizacion_id': cotizacion_id,
        'solicitud_id': solicitud_data['solicitud_id'],
        'client_id': solicitud_data['client_id'],
        'servicio_solicitado': solicitud_data['servicio_solicitado'],
        'total_price': total_price,
        'estado': 'GENERADA',
        'fecha_generacion': datetime.now().isoformat(),
        'lineas_detalle': [
            {'descripcion': f"Servicio base: {solicitud_data['servicio_solicitado']}", 'costo': service_cost},
            {'descripcion': 'Margen Prodirtec', 'costo': service_cost * (margin - 1)}
        ]
    }
    return cotizacion



def handler(event, context):
    """
    Maneja eventos de EventBridge (para generación automática) y HTTP (para consulta/ajuste/aprobación).
    """
    print(f"Received event: {json.dumps(event)}")
    
    # Determinar si es un evento HTTP (API Gateway) o EventBridge
    if 'httpMethod' in event:
        return handle_http_request(event)
    elif 'source' in event and event['source'] == 'prodirtec.cotizaciones.solicitudes':
        return handle_eventbridge_event(event)
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'message': 'Tipo de evento no soportado.'}),
            'headers': {'Content-Type': 'application/json'}
        }


def handle_http_request(event):
    """
    Maneja las solicitudes HTTP para consulta, ajuste y aprobación de cotizaciones.
    """
    http_method = event.get('httpMethod')
    # path_parameters = event.get('pathParameters', {})
    # cotizacion_id = path_parameters.get('cotizacion_id')
    path = event.get('path')
    path_parameters = event.get('pathParameters', {})
    cotizacion_id = path_parameters.get('cotizacion_id')

    try:
    #     conn = get_db_connection()
    #     with conn.cursor() as cur:
    #         if http_method == 'GET' and cotizacion_id:
    #             cur.execute("SELECT cotizacion_id, solicitud_id, client_id, fecha_generacion, total_neto, estado, enlace_pdf_s3 FROM cotizaciones WHERE cotizacion_id = %s", (cotizacion_id,))
    #             cotizacion = cur.fetchone()
    #             if cotizacion:
    #                 # Convertir el resultado a un diccionario para JSON
    #                 columns = [desc[0] for desc in cur.description]
    #                 cotizacion_dict = dict(zip(columns, cotizacion))
    #                 return {
    #                     'statusCode': 200,
    #                     'body': json.dumps(cotizacion_dict),
    #                     'headers': {'Content-Type': 'application/json'}
    #                 }
    #             return {
    #                 'statusCode': 404,
    #                 'body': json.dumps({'message': 'Cotización no encontrada.'}),
    #                 'headers': {'Content-Type': 'application/json'}
    #             }
            
    #         elif http_method == 'PUT' and cotizacion_id and event['path'].endswith('/ajustar'):
    #             body = json.loads(event['body'])
    #             # Lógica para actualizar la cotización en DB
    #             # Validar que solo los campos permitidos sean actualizados
    #             cur.execute("UPDATE cotizaciones SET total_neto = %s, estado = %s, fecha_ultima_actualizacion = %s WHERE cotizacion_id = %s",
    #                         (body.get('total_neto'), 'AJUSTE_SOLICITADO', datetime.now().isoformat(), cotizacion_id))
    #             conn.commit()
    #             eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAjustada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
    #             return {
    #                 'statusCode': 200,
    #                 'body': json.dumps({'message': 'Cotización ajustada y pendiente de revisión.'}),
    #                 'headers': {'Content-Type': 'application/json'}
    #             }

    #         elif http_method == 'POST' and cotizacion_id and event['path'].endswith('/aprobar'):
    #             cur.execute("UPDATE cotizaciones SET estado = %s, fecha_ultima_actualizacion = %s WHERE cotizacion_id = %s",
    #                         ('APROBADA', datetime.now().isoformat(), cotizacion_id))
    #             conn.commit()
    #             eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAprobada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
    #             return {
    #                 'statusCode': 200,
    #                 'body': json.dumps({'message': 'Cotización aprobada.'}),
    #                 'headers': {'Content-Type': 'application/json'}
    #             }
            
    #         else:
    #             return {
    #                 'statusCode': 400,
    #                 'body': json.dumps({'message': 'Método o ruta no soportada.'}),
    #                 'headers': {'Content-Type': 'application/json'}
    #             }

        if cotizacion_id:
            if http_method == 'GET':
                response = cotizaciones_table.get_item(Key={'cotizacion_id': cotizacion_id})
                item = response.get('Item')
                if item:
                    return {'statusCode': 200, 'body': json.dumps(item)}
                return {'statusCode': 404, 'body': json.dumps({'message': 'Cotización no encontrada'})}
            
            elif http_method == 'PUT' and path.endswith('/ajustar'):
                # Lógica para ajustar cotización en DynamoDB (UPDATE)
                body = json.loads(event['body'])
                cotizaciones_table.update_item(
                    Key={'cotizacion_id': cotizacion_id},
                    UpdateExpression="SET ajuste = :a, #est = :estado",
                    ExpressionAttributeValues={':a': body.get('ajuste', 0), ':estado': 'AJUSTADA'},
                    ExpressionAttributeNames={'#est': 'estado'}
                )
                # Emitir evento CotizacionAjustada
                eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAjustada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
                return {'statusCode': 200, 'body': json.dumps({'message': 'Cotización ajustada'})}

            elif http_method == 'POST' and path.endswith('/aprobar'):
                # Lógica para ajustar cotización en DynamoDB (CREATE)
                body = json.loads(event['body'])
                cotizaciones_table.update_item(
                    Key={'cotizacion_id': cotizacion_id},
                    UpdateExpression="SET ajuste = :a, #est = :estado",
                    ExpressionAttributeValues={':a': body.get('ajuste', 0), ':estado': 'APROBADA'},
                    ExpressionAttributeNames={'#est': 'estado'}
                )
                # Emitir evento CotizacionAprobada
                eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAprobada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
                return {'statusCode': 200, 'body': json.dumps({'message': 'Cotización aprobada'})}
        
        return {'statusCode': 400, 'body': json.dumps({'message': 'Ruta HTTP no válida'})}

    except Exception as e:
        print(f"API Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': f'Error interno del servidor: {str(e)}'}),
            'headers': {'Content-Type': 'application/json'}
        }


def handle_eventbridge_event(event):
    """
    Maneja el evento "CotizacionSolicitada" de EventBridge para generar una cotización.
    """
    try:
        detail_type = event.get('detail-type')
        # if detail_type == 'CotizacionSolicitada':
        #     solicitud_data = json.loads(event['detail'])
        #     solicitud_id = solicitud_data['solicitud_id']
        #     client_id = solicitud_data['client_id']
        #     servicio_solicitado_nombre = solicitud_data.get('servicio_solicitado')

        #     conn = get_db_connection()
        #     with conn.cursor() as cur:
        #         # 1. Obtener información del servicio
        #         cur.execute("SELECT id, nombre, precio_base, unidad_medida FROM servicios WHERE nombre = %s", (servicio_solicitado_nombre,))
        #         servicio_info = cur.fetchone()
                
        #         if not servicio_info:
        #             print(f"Servicio '{servicio_solicitado_nombre}' no encontrado. No se puede generar cotización.")
        #             # Opcional: emitir un evento de error
        #             return {'statusCode': 500, 'body': json.dumps({'message': 'Servicio no encontrado para cotización'})}

        #         servicio_id, nombre_servicio, precio_base, unidad_medida = servicio_info
                
        #         # 2. Calcular la cotización (simplificado: precio base + 18% de impuesto)
        #         cotizacion_id = str(uuid.uuid4())
        #         cantidad = 1 # Asumimos 1 unidad para la demostración
        #         subtotal = precio_base * cantidad
        #         impuestos_porcentaje = 0.18
        #         total_neto = subtotal * (1 + impuestos_porcentaje)
                
        #         fecha_generacion = datetime.now().isoformat()

        #         # 3. Guardar cotización en la BD
        #         cur.execute(
        #             "INSERT INTO cotizaciones (cotizacion_id, solicitud_id, client_id, fecha_generacion, total_neto, estado, enlace_pdf_s3, fecha_ultima_actualizacion) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        #             (cotizacion_id, solicitud_id, client_id, fecha_generacion, total_neto, 'GENERADA', '', fecha_generacion))
                
        #         cur.execute(
        #             "INSERT INTO cotizacion_lineas (cotizacion_id, servicio_id, descripcion, cantidad, precio_unitario, subtotal) VALUES (%s, %s, %s, %s, %s, %s)",
        #             (cotizacion_id, servicio_id, nombre_servicio, cantidad, precio_base, subtotal))
                
        #         conn.commit()
                
        #         # 4. Generar PDF y subir a S3
        #         cotizacion_pdf_data = {
        #             'cotizacion_id': cotizacion_id,
        #             'client_id': client_id,
        #             'servicio_solicitado': nombre_servicio,
        #             'detalles': solicitud_data.get('detalles', ''),
        #             'fecha_generacion': fecha_generacion,
        #             'total_neto': total_neto,
        #             'lineas_cotizacion': [
        #                 {'descripcion': nombre_servicio, 'cantidad': cantidad, 'unidad': unidad_medida, 'precio_unitario': precio_base, 'subtotal': subtotal}
        #             ]
        #         }
        #         pdf_buffer = generate_cotizacion_pdf(cotizacion_pdf_data, cotizacion_id)
                
        #         pdf_key = f"cotizaciones/{cotizacion_id}.pdf"
        #         s3.put_object(Bucket=S3_BUCKET_NAME, Key=pdf_key, Body=pdf_buffer.getvalue(), ContentType='application/pdf')
                
        #         s3_url = f"https://{S3_BUCKET_NAME}.s3.sa-east-1.amazonaws.com/{pdf_key}"
                
        #         # 5. Actualizar cotización con URL del PDF
        #         cur.execute("UPDATE cotizaciones SET enlace_pdf_s3 = %s WHERE cotizacion_id = %s", (s3_url, cotizacion_id))
        #         conn.commit()

        if event.get('detail-type') == 'CotizacionSolicitada':
            detail = event['detail']
            solicitud_id = detail['solicitud_id']
            client_id = detail['client_id']
            
            # 1. Simular la obtención de datos de la solicitud de un servicio externo (o se podría pasar más data en el evento)
            solicitud_data = detail
            
            # 2. Generar datos de cotización (reemplaza la lógica de DB relacional)
            cotizacion = generate_quote_data(solicitud_data)
            cotizacion_id = cotizacion['cotizacion_id']
            
            # 3. Guardar la cotización en DynamoDB (reemplaza INSERT/COMMIT en Aurora)
            cotizaciones_table.put_item(Item=cotizacion)

            # 4. Generar PDF y subir a S3 (SIN CAMBIOS)
            pdf_buffer = generate_cotizacion_pdf(cotizacion)
            pdf_key = f"cotizaciones/{cotizacion_id}.pdf"
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=pdf_key, Body=pdf_buffer.getvalue(), ContentType='application/pdf')
            
            # CRÍTICO: CAMBIO DE REGIÓN EN LA URL
            s3_url = f"https://{S3_BUCKET_NAME}.s3.us-east-1.amazonaws.com/{pdf_key}" # <-- CAMBIO DE sa-east-1 A us-east-1
            
            # 5. Actualizar cotización con URL del PDF en DynamoDB (reemplaza UPDATE en Aurora)
            cotizaciones_table.update_item(
                Key={'cotizacion_id': cotizacion_id},
                UpdateExpression="SET enlace_pdf_s3 = :url, #est = :estado",
                ExpressionAttributeValues={':url': s3_url, ':estado': 'COMPLETADA'},
                ExpressionAttributeNames={'#est': 'estado'}
            )

            # 6. Enviar evento "CotizacionGenerada"
            eventbridge.put_events(
                Entries=[
                    {
                        'Source': 'prodirtec.cotizaciones',
                        'DetailType': 'CotizacionGenerada',
                        'Detail': json.dumps({'cotizacion_id': cotizacion_id, 'solicitud_id': solicitud_id, 'enlace_pdf': s3_url, 'client_id': client_id}),
                        'EventBusName': EVENT_BUS_NAME
                    }
                ]
            )
            return {'statusCode': 200, 'body': json.dumps({'cotizacion_id': cotizacion_id, 'enlace_pdf': s3_url})}

        return {'statusCode': 200, 'body': json.dumps({'message': 'Event processed, no action taken.'})} # Default for EventBridge
    except Exception as e:
        print(f"EventBridge Handler Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'message': str(e)})}