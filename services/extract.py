import os
import json
from utilities.etc import p_print, Colours

CREDENTIALS_FOLDER = "./credentials"
OUTPUT_FILE = "credentials.txt"


def extract_credentials(account_format: str = "{email}#{password}"):
	# An empty format (the default in config.json) means "use the default
	# text template" rather than writing blank lines, mirroring the JSON
	# per-account default used by save_credentials.
	if not account_format:
		account_format = "{email}#{password}"

	if not os.path.isdir(CREDENTIALS_FOLDER):
		p_print("No credentials folder found, nothing to extract.", Colours.FAIL)
		return

	json_files = [
		f
		for f in os.listdir(CREDENTIALS_FOLDER)
		if f.endswith(".json") and os.path.isfile(os.path.join(CREDENTIALS_FOLDER, f))
	]
	p_print(f"Extracting {len(json_files)} account(s)...", Colours.OKCYAN)

	with open(OUTPUT_FILE, "w") as output_file:
		for file in json_files:
			file_path = os.path.join(CREDENTIALS_FOLDER, file)

			with open(file_path, "r") as json_file:
				try:
					data = json.load(json_file)
				except json.JSONDecodeError:
					p_print(
						f"Failed to parse JSON file: {file}, skipping...",
						Colours.WARNING,
					)
					continue

			email = data.get("email", "")
			password = data.get("password", "")
			emailPassword = data.get("emailPassword", "")

			# Replace placeholders in the account_format string with actual values
			output = (
				account_format.replace("{email}", email)
				.replace("{password}", password)
				.replace("{emailPassword}", emailPassword)
			)

			output_file.write(f"{output}\n")
			p_print(f"  + {email}", Colours.OKCYAN)

	p_print("Data extraction and writing complete!", Colours.OKGREEN)
	p_print(f"Output saved to: {os.path.abspath(OUTPUT_FILE)}", Colours.OKGREEN)
