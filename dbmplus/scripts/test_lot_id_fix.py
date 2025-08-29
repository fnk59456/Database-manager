#!/usr/bin/env python3
"""
測試批次ID提取邏輯的修正
"""

def test_lot_id_extraction():
    """測試批次ID提取邏輯"""
    print("測試批次ID提取邏輯")
    print("=" * 50)
    
    # 測試案例
    test_cases = [
        {
            "lot_id": "temp_WLPF800300",
            "expected": "WLPF800300"
        },
        {
            "lot_id": "temp_WLPF800301",
            "expected": "WLPF800301"
        },
        {
            "lot_id": "WLPF800300",
            "expected": "WLPF800300"
        },
        {
            "lot_id": "other_prefix_WLPF800300",
            "expected": "other_prefix_WLPF800300"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n測試案例 {i}:")
        print(f"  輸入 lot_id: {case['lot_id']}")
        print(f"  期望結果: {case['expected']}")
        
        # 應用修正後的邏輯
        if case['lot_id'].startswith("temp_"):
            original_lot_id = case['lot_id'][5:]  # 移除 "temp_" 前綴
        else:
            original_lot_id = case['lot_id']
        
        print(f"  實際結果: {original_lot_id}")
        print(f"  測試結果: {'✅ 通過' if original_lot_id == case['expected'] else '❌ 失敗'}")
    
    print("\n" + "=" * 50)
    print("測試完成")

if __name__ == "__main__":
    test_lot_id_extraction()



