import re
import json
from bson import ObjectId


def parse_id(log_entry):
    # Extract the _id value using a regular expression
    id_pattern = r'\"_id\":\s*\{"(\$oid)"\:\s*"([^"]+)"'
    match = re.search(id_pattern, log_entry)

    if match:
        id_type = match.group(1)
        id_value = match.group(2)
        print(f"ID Type: {id_type}")
        print(f"ID Value: {id_value}")
    else:
        print("ID not found in the log entry.")


def process_large_log_file(file_path, json_output_file, batch_size=1000):
    # Patterns for fields in "pymongo.command DEBUG" log lines
    command_pattern = re.compile(r'pymongo.command DEBUG.*?{(.*)}')
    # Regex patterns for the fields we want to extract
    block_id_pattern = re.compile(r'\\"block_id\\": \[(.*?),\s*(\d+)\]')
    read_roi_pattern = re.compile(r'\\"read_roi\\": \[\[(.*?)\]\]')
    write_roi_pattern = re.compile(r'\\"write_roi\\": \[\[(.*?)\]\]')
    start_pattern = re.compile(r'\\"start\\": ([\d.]+)')
    duration_pattern = re.compile(r'\\"duration\\": ([\d.]+)')
    id_pattern = re.compile( r'\\"_id\\":\s*\{\\"(\$oid)\\"\\:\s*"([^"]+})"')
    extracted_data = []

    def parse_log_entry(log_entry):
        # Extract the required fields from the JSON-like string
        # log_entry = f"'''{log_entry}'''"
        block_id = block_id_pattern.search(log_entry)
        read_roi = read_roi_pattern.search(log_entry)
        write_roi = write_roi_pattern.search(log_entry)
        start = start_pattern.search(log_entry)
        duration = duration_pattern.search(log_entry)
        log_id = id_pattern.search(log_entry)

        if all([block_id, read_roi, write_roi, start, duration, log_id]):
            # Ensure the second value in `block_id` is a number
            block_id_parts = [x.strip().strip('"') for x in block_id.group(1).split(',')]
            block_id_parts[1] = int(block_id_parts[1])

            return {
                '_id': str(ObjectId(log_id.group(1))),  # Convert ObjectId to string for JSON compatibility
                'block_id': block_id_parts,
                'read_roi': [[int(x) for x in pair.split(',')] for pair in read_roi.group(1).split('],[')],
                'write_roi': [[int(x) for x in pair.split(',')] for pair in write_roi.group(1).split('],[')],
                'start': float(start.group(1)),
                'duration': float(duration.group(1))
            }
        return None

    with open(file_path, 'r') as file:
        buffer = []
        for line in file:
            # Search for pymongo.command DEBUG lines
            match = command_pattern.search(line)
            if match:
                buffer.append(match.group(1))  # Accumulate log entry
                log_text = ' '.join(buffer)  # Join buffer contents

                # Parse log entry and reset buffer
                parsed_entry = parse_log_entry(log_text)
                if parsed_entry:
                    extracted_data.append(parsed_entry)
                buffer = []  # Clear buffer after parsing

                # Process data in batches
                if len(extracted_data) >= batch_size:
                    save_to_json(extracted_data, json_output_file)
                    extracted_data = []  # Clear the batch

        # Process remaining data after the file ends
        if extracted_data:
            save_to_json(extracted_data, json_output_file)


def save_to_json(data, json_output_file):
    # Append the batch of data to the JSON file
    with open(json_output_file, 'a') as f:
        for entry in data:
            json.dump(entry, f)
            f.write('\n')  # Each document on a new line (for easier MongoDB loading)


def load_json_to_mongo(json_file_path, mongo_uri, db_name, collection_name):
    from pymongo import MongoClient

    # Set up MongoDB connection
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    # Read JSON file and insert into MongoDB
    with open(json_file_path, 'r') as f:
        for line in f:
            document = json.loads(line)
            document['_id'] = ObjectId(document['_id'])  # Convert _id back to ObjectId
            collection.insert_one(document)

    print(f"Data inserted successfully into {db_name}.{collection_name}")


# Example usage:
log_file_path = '/media/samia/DATA/ark/connexion/codebases/restructured_packages/local_shape_descriptors/logs/predict_scan_logs_2024-05-19 08:42:19.641007.txt'
json_output_file = './predict_scan_logs_2024-05-1908:42:19.641007_extracted_data.json'
process_large_log_file(log_file_path, json_output_file, batch_size=1000)

# Later, you can load the JSON file into MongoDB using this function:
# mongo_uri = "mongodb://localhost:27017/"
# db_name = "log_database"
# collection_name = "log_entries"
# load_json_to_mongo(json_output_file, mongo_uri, db_name, collection_name)
