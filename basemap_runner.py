import pandas as pd
import os
import json
import matplotlib.pyplot as plt

def load_formula_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def get_filtered_data(file_path, mask_rules_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        return None

    df = pd.read_csv(file_path)

    if 'Row' not in df.columns or 'Col' not in df.columns:
        print(f"Warning: Missing 'Row' or 'Col' columns in {file_path}. Returning original data.")
        return df

    if os.path.exists(mask_rules_path):
        with open(mask_rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)

        for rule in rules:
            try:
                start_row = int(rule["start_row"])
                end_row = int(rule["end_row"])
                start_col = int(rule["start_col"])
                end_col = int(rule["end_col"])
                df = df.drop(df[(df['Row'] >= start_row) & (df['Row'] <= end_row) &
                                (df['Col'] >= start_col) & (df['Col'] <= end_col)].index)
            except KeyError as e:
                print(f"Rule is missing a key: {e}")
            except TypeError as e:
                print(f"Invalid rule format: {e}")

    return df

def process_csv(df, total_count):
    if df is None or df.empty:
        return pd.DataFrame()

    if 'DefectType' not in df.columns:
        print("Warning: 'DefectType' column not found. Returning empty DataFrame.")
        return pd.DataFrame()

    defect_counts = df['DefectType'].value_counts()
    defect_percentage = (defect_counts / total_count)

    return pd.DataFrame({
        'DefectType': defect_counts.index,
        'Count': defect_counts.values,
        'Percentage': defect_percentage.values
    })

def generate_map(df, output_path, selection, plot_config_path):
    plot_config = json.load(open(plot_config_path, encoding="utf-8"))

    map_configurations = plot_config.get('map_configurations', {})
    map_size = tuple(plot_config.get('map_size', (20, 20)))
    original_size = plot_config.get('original_size', 100)
    title_fontsize = plot_config.get('title_fontsize', 20)
    invert_x_axis = plot_config.get('invert_x_axis', False)

    config = map_configurations.get(selection, map_configurations.get('MT', {}))
    color_map = config.get('colors', {})

    df_sorted = df.sort_values(by=['Col', 'Row'])
    fig, ax = plt.subplots(figsize=map_size)
    fig.subplots_adjust(left=0.07, right=0.93, bottom=0.07, top=0.93)

    reduced_size = original_size / 15

    for defect_type, color in color_map.items():
        if defect_type in df['DefectType'].unique():
            subset = df_sorted[df_sorted['DefectType'] == defect_type]
            ax.scatter(subset['Col'], subset['Row'], c=color, label=defect_type, s=reduced_size, alpha=0.6, edgecolors='w')

    ax.set_xlabel('Col Coordinate')
    ax.set_ylabel('Row Coordinate')
    file_name = os.path.basename(output_path).replace(".png", "")
    ax.set_title(f'Map of Defects - {file_name}', fontsize=title_fontsize)
    ax.legend(title='Defect Type', loc='center left', bbox_to_anchor=(1, 0.5))

    ax.invert_yaxis()
    if invert_x_axis:
        ax.invert_xaxis()

    plt.savefig(output_path, bbox_inches='tight')
    print(f"✅ Basemap saved: {output_path}")
    plt.close()

def run_basemap(csv_path, stage, product, lot, config):
    output_dir = os.path.join(config["path_pattern"]["map"].format(product=product, lot=lot),stage ) # 加上站點名稱 
    os.makedirs(output_dir, exist_ok=True)

    sample_rules = json.load(open("configs/sample_rules.json", encoding="utf-8"))
    rule = sample_rules.get(stage, {})
    formula_path = rule["formulas"]
    mask_path = rule["mask"]
    plot_path = rule["plot"]

    formula_data = load_formula_json(formula_path)
    total_count = formula_data["Total Count"]

    df = get_filtered_data(csv_path, mask_path)
    if df is None or df.empty:
        print(f"⚠️ Basemap skipped: {os.path.basename(csv_path)} is empty.")
        return

    result = process_csv(df, total_count)
    if result.empty:
        print(f"⚠️ Basemap result is empty: {os.path.basename(csv_path)}")
        return

    filename = os.path.splitext(os.path.basename(csv_path))[0] + ".png"
    output_path = os.path.join(output_dir, filename)
    generate_map(df, output_path, stage, plot_path)
