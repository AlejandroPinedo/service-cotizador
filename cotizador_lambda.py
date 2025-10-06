# service-cotizador/cotizador_lambda.py
import json
import os
import boto3
import uuid
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

# --- Clientes de AWS ---
s3 = boto3.client('s3')
eventbridge = boto3.client('events')
dynamodb = boto3.resource('dynamodb')

# --- Variables de Entorno y Recursos ---
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
EVENT_BUS_NAME = os.environ['EVENT_BUS_NAME']
cotizaciones_table = dynamodb.Table(os.environ['COTIZACIONES_TABLE_NAME'])

def generate_cotizacion_pdf(cotizacion_data, cotizacion_id):
    """
    Genera un PDF para la cotización con los datos proporcionados.
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

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

    total_general = 0
    # ✅ CORREGIDO: Usa 'lineas_cotizacion' y asegura que el PDF reciba todos los campos necesarios.
    for line in cotizacion_data.get('lineas_cotizacion', []):
        subtotal = line.get('subtotal', 0)
        total_general += subtotal
        c.drawString(100, y_pos, f"{line.get('descripcion', 'N/A'):<25} {line.get('cantidad', 0):>10.2f} {line.get('unidad', 'N/A'):<10} ${line.get('precio_unitario', 0):>15.2f} ${subtotal:>10.2f}")
        y_pos -= 15

    y_pos -= 20
    c.drawString(350, y_pos, f"Total Neto: ${total_general:,.2f}")

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer

def generate_quote_data(solicitud_data):
    """
    Lógica de negocio para generar los datos de una cotización.
    """
    service_cost = 5000
    margin = 1.2
    cotizacion_id = str(uuid.uuid4())
    total_price = service_cost * margin

    cotizacion = {
        'cotizacion_id': cotizacion_id,
        'solicitud_id': solicitud_data['solicitud_id'],
        'client_id': solicitud_data['client_id'],
        'servicio_solicitado': solicitud_data['servicio_solicitado'],
        'detalles': solicitud_data.get('detalles', 'Servicio estándar'),
        'total_price': total_price,
        'estado': 'GENERADA',
        'fecha_generacion': datetime.now().isoformat(),
        # ✅ CORREGIDO: Clave 'lineas_cotizacion' y estructura completa para el PDF.
        'lineas_cotizacion': [
            {
                'descripcion': f"Servicio: {solicitud_data['servicio_solicitado']}",
                'cantidad': 1,
                'unidad': 'Unid.',
                'precio_unitario': service_cost,
                'subtotal': service_cost
            },
            {
                'descripcion': 'Margen/Gestión',
                'cantidad': 1,
                'unidad': 'Unid.',
                'precio_unitario': service_cost * (margin - 1),
                'subtotal': service_cost * (margin - 1)
            }
        ]
    }
    return cotizacion

def handler(event, context):
    """
    Manejador principal que enruta eventos de API Gateway o EventBridge.
    """
    print(f"Received event: {json.dumps(event)}")
    if 'httpMethod' in event:
        return handle_http_request(event)
    elif 'source' in event and event['source'] == 'prodirtec.cotizaciones.solicitudes':
        return handle_eventbridge_event(event)
    else:
        return {'statusCode': 400, 'body': json.dumps({'message': 'Tipo de evento no soportado.'})}

def handle_http_request(event):
    """
    Maneja las solicitudes HTTP para API Gateway.
    """
    http_method = event.get('httpMethod')
    path = event.get('path')
    path_parameters = event.get('pathParameters', {})
    cotizacion_id = path_parameters.get('cotizacion_id')

    if not cotizacion_id:
        return {'statusCode': 400, 'body': json.dumps({'message': 'Falta el cotizacion_id en la ruta.'})}

    try:
        if http_method == 'GET':
            response = cotizaciones_table.get_item(Key={'cotizacion_id': cotizacion_id})
            item = response.get('Item')
            if item:
                return {'statusCode': 200, 'body': json.dumps(item)}
            return {'statusCode': 404, 'body': json.dumps({'message': 'Cotización no encontrada'})}

        elif http_method == 'PUT' and path.endswith('/ajustar'):
            body = json.loads(event['body'])
            cotizaciones_table.update_item(
                Key={'cotizacion_id': cotizacion_id},
                UpdateExpression="SET ajuste = :a, #est = :estado",
                ExpressionAttributeValues={':a': body.get('ajuste', {}), ':estado': 'AJUSTADA'},
                ExpressionAttributeNames={'#est': 'estado'}
            )
            eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAjustada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
            return {'statusCode': 200, 'body': json.dumps({'message': 'Cotización ajustada'})}

        elif http_method == 'POST' and path.endswith('/aprobar'):
            # ✅ CORREGIDO: Lógica de actualización simplificada solo para cambiar el estado.
            cotizaciones_table.update_item(
                Key={'cotizacion_id': cotizacion_id},
                UpdateExpression="SET #est = :estado",
                ExpressionAttributeValues={':estado': 'APROBADA'},
                ExpressionAttributeNames={'#est': 'estado'}
            )
            eventbridge.put_events(Entries=[{'Source': 'prodirtec.cotizaciones', 'DetailType': 'CotizacionAprobada', 'Detail': json.dumps({'cotizacion_id': cotizacion_id}), 'EventBusName': EVENT_BUS_NAME}])
            return {'statusCode': 200, 'body': json.dumps({'message': 'Cotización aprobada'})}

        return {'statusCode': 400, 'body': json.dumps({'message': 'Ruta o método HTTP no válido'})}

    except Exception as e:
        print(f"API Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'message': f'Error interno del servidor: {str(e)}'})}

def handle_eventbridge_event(event):
    """
    Maneja el evento 'CotizacionSolicitada' para generar una cotización.
    """
    try:
        if event.get('detail-type') == 'CotizacionSolicitada':
            solicitud_data = event['detail']

            # 1. Generar datos de la cotización
            cotizacion = generate_quote_data(solicitud_data)
            cotizacion_id = cotizacion['cotizacion_id']

            # 2. Guardar la cotización en DynamoDB
            cotizaciones_table.put_item(Item=cotizacion)

            # 3. Generar PDF y subir a S3
            pdf_buffer = generate_cotizacion_pdf(cotizacion, cotizacion_id)
            pdf_key = f"cotizaciones/{cotizacion_id}.pdf"
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=pdf_key, Body=pdf_buffer.getvalue(), ContentType='application/pdf')

            # ✅ CORREGIDO: URL de S3 dinámica para funcionar en cualquier región.
            region = s3.meta.region_name
            s3_url = f"https://{S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{pdf_key}"

            # 4. Actualizar el item en DynamoDB con la URL del PDF
            cotizaciones_table.update_item(
                Key={'cotizacion_id': cotizacion_id},
                UpdateExpression="SET enlace_pdf_s3 = :url",
                ExpressionAttributeValues={':url': s3_url}
            )

            # 5. Enviar evento 'CotizacionGenerada'
            eventbridge.put_events(
                Entries=[{
                    'Source': 'prodirtec.cotizaciones',
                    'DetailType': 'CotizacionGenerada',
                    'Detail': json.dumps({
                        'cotizacion_id': cotizacion_id,
                        'solicitud_id': solicitud_data['solicitud_id'],
                        'enlace_pdf': s3_url,
                        'client_id': solicitud_data['client_id']
                    }),
                    'EventBusName': EVENT_BUS_NAME
                }]
            )
            return {'statusCode': 200, 'body': json.dumps({'cotizacion_id': cotizacion_id, 'enlace_pdf': s3_url})}

        return {'statusCode': 200, 'body': json.dumps({'message': 'Evento procesado, sin acción requerida.'})}
    except Exception as e:
        print(f"EventBridge Handler Error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'message': str(e)})}
