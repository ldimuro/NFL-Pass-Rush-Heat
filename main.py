import numpy as np
# import get_data
# from passing_down import PassingDown
# import random_tree
# import fnn
import time
import pandas as pd
import os
# from fnn import FNN
import data_processing
import get_data
import torch
import random
from sklearn.utils import check_random_state
import matplotlib.pyplot as plt
import visualization
import random
import math
import constants
import pickle
from cnn import cross_validation, BasicCNN
from torch.utils.data import TensorDataset, DataLoader


def set_seed(seed_value=42):
    random.seed(seed_value)
    np.random.seed(seed_value)
    torch.manual_seed(seed_value)
    torch.cuda.manual_seed_all(seed_value)
    check_random_state(seed_value)


def main():
    print('running main')
    # set_seed()

    is_data_processing = True
    process_tensors = False
    is_test_set = False

    all_player_data = get_data.get_player_data(year=2022)
    all_player_data_2021 = get_data.get_player_data(year=2021)
    all_player_data_2018 = get_data.get_player_data(year=2018)




    # testing = [23.342, 34.634, 32.373, 42.325, 54.235, 64.432, 57.456, 60.536, 62.426, 63.643]
    # rolling_avg_backward = [np.mean(testing[i-2:i+1]) for i in range(2, len(testing))]
    # print('testing:', rolling_avg_backward)
    # for i in range(len(testing)):







    if is_data_processing:

        # Obtain all play and tracking data
        all_tracking_data = get_data.get_tracking_data(year=2022, week_start=1, week_end=1)         # 9
        all_tracking_data_2021 = get_data.get_tracking_data(year=2021, week_start=1, week_end=8)    # 8
        all_tracking_data_2018 = get_data.get_tracking_data(year=2018, week_start=1, week_end=1)   # 17
        # all_tracking_df = pd.concat(all_tracking_data, ignore_index=True)
        # all_tracking_df_2021 = pd.concat(all_tracking_data_2021, ignore_index=True)
        all_play_data = get_data.get_play_data(year=2022)
        all_play_data_2021 = get_data.get_play_data(year=2021)
        all_play_data_2018 = get_data.get_play_data(year=2018)
        # all_player_play_data = get_data.get_player_play_data(year=2022)

        

        # MAIN EXAMPLE: in (2021091206, 3353), 81 has a higher potential for yards, but QB throws to 28 instead
        # (2022091104, 3956): Goff could've passed it to 14 earlier and gotten a much larger gain
        # Good example (2022091104, 3204), (2022091100, 458), (2022091105, 4905), (2022091109, 743), (2022091112, 917)
        passing_play_data_2021 = all_play_data_2021[(all_play_data_2021['passResult'] == 'C') &
                                                    (all_play_data_2021['playDescription'].str.contains('short', case=False, na=False))]# & (all_play_data_2021['playResult'] <= 3)]
        passing_tracking_data_2021 = data_processing.filter_tracking_data(all_tracking_data_2021, passing_play_data_2021)
        passing_tracking_data_2021 = data_processing.normalize_field_direction(passing_tracking_data_2021)
        passing_tracking_data_2021 = data_processing.normalize_to_center(passing_tracking_data_2021)


        passing_play_data_2018 = all_play_data_2018[(all_play_data_2018['passResult'] == 'C') &
                                                    (all_play_data_2018['playDescription'].str.contains('short', case=False, na=False))]# & (all_play_data_2018['playResult'] <= 3)]
        passing_tracking_data_2018 = data_processing.filter_tracking_data(all_tracking_data_2018, passing_play_data_2018)
        passing_tracking_data_2018 = data_processing.normalize_field_direction(passing_tracking_data_2018)
        passing_tracking_data_2018 = data_processing.normalize_to_center(passing_tracking_data_2018)

        
        # Filter to include only pass plays that were thrown within 1 yards of the LoS
        passing_play_data = all_play_data[all_play_data['passResult'].notna()]
        passes_behind_los_play_data = passing_play_data[(passing_play_data['passResult'] == 'C') & 
                                                        (passing_play_data['passLength'] <= 2) &
                                                        (passing_play_data['passTippedAtLine'] == False) &
                                                        (passing_play_data['playNullifiedByPenalty'] == 'N')]# &
                                                        # (passing_play_data['targetY'] >= constants.SIDELINE_TO_HASH / 2) &
                                                        # (passing_play_data['targetY'] < constants.FIELD_WIDTH - constants.SIDELINE_TO_HASH / 2)]
        passes_behind_los_tracking_data = data_processing.filter_tracking_data(all_tracking_data, passes_behind_los_play_data)
        passes_behind_los_tracking_data = data_processing.normalize_field_direction(passes_behind_los_tracking_data)
        passes_behind_los_tracking_data = data_processing.normalize_to_center(passes_behind_los_tracking_data)
        

        # print('# of passing plays:', len(passing_play_data))
        # print('# of passing plays behind LoS:', len(passes_behind_los_play_data))
        # print('#\t Average EPA on passes behind LoS:' ,passes_behind_los_play_data['expectedPointsAdded'].mean())

        # median_yardsGained_yardsToGo_ratio = (passes_behind_los_play_data['yardsGained'] / passes_behind_los_play_data['yardsToGo']).median()
        # plays_above_yardsGained_yardsToGo_ratio = passes_behind_los_play_data[(passes_behind_los_play_data['yardsGained']/passes_behind_los_play_data['yardsToGo']) >= median_yardsGained_yardsToGo_ratio]
        # print('#\t Mean yardsGained/yardsToGo ratio on passes behind LoS:', median_yardsGained_yardsToGo_ratio)
        # print('#\t Percent of behind LoS passes >= median_yardsGained_yardsToGo_ratio:', len(plays_above_yardsGained_yardsToGo_ratio) / len(passes_behind_los_play_data))
        # print('#\t Max yardsGained on passes behind LoS:', passes_behind_los_play_data['yardsGained'].max())
        # print('# of 2021 passing plays:', len(all_play_data_2021))


        # behind_los_play_data_2021 = data_processing.get_data_at_pass_forward(passing_play_data_2021, passing_tracking_data_2021, all_player_data_2021)
        # print(f'PLAYS EXTRACTED {len(behind_los_play_data_2021)}/{len(passing_play_data_2021)}')
        # data_processing.save_data(behind_los_play_data_2021, 'behind_los_play_data_2021_weeks1-8')
        # behind_los_play_data_2021_augmented = data_processing.augment_data(behind_los_play_data_2021)
        # data_processing.save_data(behind_los_play_data_2021_augmented, 'behind_los_play_data_2021_weeks1-8_augmented')

        # behind_los_play_data_2022 = data_processing.get_data_at_pass_forward(passes_behind_los_play_data, passes_behind_los_tracking_data, all_player_data)
        # print(f'PLAYS EXTRACTED {len(behind_los_play_data_2022)}/{len(passes_behind_los_play_data)}')
        # data_processing.save_data(behind_los_play_data_2022, 'behind_los_play_data_2022_weeks1-9')
        # behind_los_play_data_2022_augmented = data_processing.augment_data(behind_los_play_data_2022)
        # data_processing.save_data(behind_los_play_data_2022_augmented, 'behind_los_play_data_2022_weeks1-9_augmented')

        # behind_los_play_data_2018 = data_processing.get_data_at_pass_forward(passing_play_data_2018, passing_tracking_data_2018, all_player_data_2018)
        # print(f'PLAYS EXTRACTED {len(behind_los_play_data_2018)}/{len(passing_play_data_2018)}')
        # data_processing.save_data(behind_los_play_data_2018, 'behind_los_play_data_2018_weeks1-17')
        # behind_los_play_data_2018_augmented = data_processing.augment_data(behind_los_play_data_2018)
        # data_processing.save_data(behind_los_play_data_2018_augmented, 'behind_los_play_data_2018_weeks1-17_augmented')



    data_2021 = data_processing.get_data('behind_los_play_data_2021_weeks1-8')  # 1142 samples
    data_2022 = data_processing.get_data('behind_los_play_data_2022_weeks1-9')  # 1985 samples
    data_2018 = data_processing.get_data('behind_los_play_data_2018_weeks1-17') # 4565 samples
    data_2021_augm = data_processing.get_data('behind_los_play_data_2021_weeks1-8_augmented')
    data_2022_augm = data_processing.get_data('behind_los_play_data_2022_weeks1-9_augmented')
    data_2018_augm = data_processing.get_data('behind_los_play_data_2018_weeks1-17_augmented')
    total_data = data_2021 | data_2022 | data_2018 | data_2021_augm | data_2022_augm | data_2018_augm

    print('data_2021:', len(data_2021))
    print('data_2022:', len(data_2022))
    print('data_2018:', len(data_2018))
    print('TOTAL DATA:', len(total_data))

    # print('AUG:\n', list(data_2021_augm)[5], data_2021_augm[list(data_2021_augm)[5]])
    # print('NON-AUG:\n', list(data_2021)[5], data_2021[list(data_2021)[5]])

    # print('AUG:\n', list(data_2022_augm)[5], data_2022_augm[list(data_2022_augm)[5]])
    # print('NON-AUG:\n', list(data_2022)[5], data_2022[list(data_2022)[5]])

    # print('AUG:\n', list(data_2018_augm)[5], data_2018_augm[list(data_2018_augm)[5]])
    # print('NON-AUG:\n', list(data_2018)[5], data_2018[list(data_2018)[5]])

    # print(total_data[(2021092604,3981)])

    count_true = sum(1 for v in total_data.values() if v.get('label') is True)
    print(f'play success ratio: {count_true/len(total_data)*100:.2f}% ({count_true}/{len(total_data)})')



    # Create tensors/labels for all sample plays
    all_players =  pd.concat([all_player_data, all_player_data_2021, all_player_data_2018])
    all_players = all_players.drop_duplicates(subset=['nflId'])
    if process_tensors:
        input_tensors, labels = data_processing.get_tensor_batch(total_data, all_players)
        data_processing.save_data(input_tensors, 'total_behind_los_pass_aug_input_tensors_dict')
        data_processing.save_data(labels, 'total_behind_los_pass_aug_labels_dict')

    

    input_tensors = data_processing.get_data('total_behind_los_pass_aug_input_tensors_dict')
    print('TOTAL INPUT TENSORS:', len(input_tensors))
    labels = data_processing.get_data('total_behind_los_pass_aug_labels_dict')
    print('TOTAL INPUT LABELS:', len(labels))





    if is_test_set:

        # - (2022091105, 2544) - No Success
        # - (2022091112, 917)  - Success
        # - (2021102403, 3496) - Success
        # - (2021100303, 1951) - No Success
        # - (2021102410, 3434) - No Success
        # - (2021091206, 3353) - MAIN EXAMPLE FOR VISUALIZATION, ADD INDICATOR FOR BOTH RECEIVERS (will need to manually add)
        withheld_use_case_plays = [(2022091105, 2544), (2022091112, 917), (2021100303, 1951), (2021102410, 3434)]

        # Randomly select 59 successful plays to use as testing set
        success_plays = [key for key, value in total_data.items() if value.get('label') is True]
        withheld_success_plays = random.sample(success_plays, 59)

        # Randomly select 41 unsuccessful plays to use as testing set
        no_success_plays = [key for key, value in total_data.items() if value.get('label') is True]
        withheld_no_success_plays = random.sample(no_success_plays, 41)

        withheld_plays = withheld_success_plays + withheld_no_success_plays + withheld_use_case_plays
        

        # PERFECT EXAMPLE OF FAILURE PREDICTION: (2022091105, 2544)
        # PERFECT OVERALL EXAMPLE (USE THIS FOR DEMONSTRATION): (2021102404, 108)
        #   - #30 is not open at the beginning of the play, but as he drifts towards the sideline he becomes open enough to get a 1st down
        #   - The QB doesn't see him however, giving time for #29 to push in closer to #30, and by the time the QB throws, 
        #     #30's covered and doesn't get the 1st down
        # PERFECT EXAMPLE OF SUCCESS PREDICTION: (2022091112, 917)
        #   - The moment #33 passes by #55 moving in the opposite direction,
        #     the Short Pass Success Probability (SPSP) shoots up
        # (2021091212, 611) - Could've thrown it earlier for a higher SPSP, but threw it later and was unsuccessful

        # FALSE POSITIVE: (2021101704, 1613): Looks like #28 can easily get 2 yards but apparently he doesn't
        # FALSE NEGATIVE: (2021091911, 127): Looks like #86 has no chance for any gain, but in the actual scenario, he breaks a tackle for a big gain
        # FALSE POSITIVE: (2021091202, 3536): Great tackle by #40


        # (2021102405, 1665): Run this play with #1 as the intended receiver and compare SPSPs with #87


        # REMOVE TEST SAMPLE:
        # test_sample = (2021092610, 1650)#(2022091100, 458) #(2022091104,3204) #(2022091110, 514)
        # test_sample_aug = (2021092610, 1650.1)#(2022091100, 458.1)#(2022091104,3204.1)#(2022091110, 514.1)
        test_sample = random.choice(list(data_2021.keys()))
        test_sample_aug = (test_sample[0], test_sample[1]+0.1)

        print(total_data[test_sample])
        withheld_sample = total_data[test_sample]
        withheld_sample_aug = total_data[test_sample_aug]
        withheld_data = {}
        input_tensors.pop(test_sample, None)
        input_tensors.pop(test_sample_aug, None)
        labels.pop(test_sample, None)
        labels.pop(test_sample_aug, None)

        withheld_data[test_sample] = withheld_sample
        withheld_data[test_sample_aug] = withheld_sample_aug
        print('input_tensors mod:', len(input_tensors))
        print('labels mod:', len(input_tensors))
        print('WITHHELD DATA:', len(withheld_data))

        # Extract every frame of the play
        test_game_id, test_play_id = test_sample
        test_play_data = passing_play_data_2021[(passing_play_data_2021['gameId'] == test_game_id) & (passing_play_data_2021['playId'] == test_play_id)]
        print(test_play_data)
        test_play_frames = data_processing.get_relevant_frames(test_play_data, passing_tracking_data_2021, start_events=[constants.BALL_SNAP], end_events=[constants.PASS_FORWARD])
        print(test_play_frames[test_sample])

        test_play_frames_data = {}
        z = test_play_frames[test_sample]
        min_frame = test_play_frames[test_sample]['frameId'].min()
        max_frame = test_play_frames[test_sample]['frameId'].max()
        print(f"Min:{min_frame}, Max:{max_frame}")
        for frame_id in range(min_frame, max_frame+1):
            data = withheld_data[test_sample].copy()
            data['tracking_data'] = z[z['frameId'] == frame_id]
            test_play_frames_data[(test_game_id, test_play_id+(frame_id*0.001))] = data

        print('TOTAL DATA FOR PLAY:', len(test_play_frames_data))
        # print(test_play_frames_data)


        test_input_tensors, test_labels = data_processing.get_tensor_batch(test_play_frames_data, all_players)
        data_processing.save_data(test_input_tensors, 'test_behind_los_pass_aug_input_tensors')
        data_processing.save_data(test_labels, 'test_behind_los_pass_aug_labels')



        # Ensure the testing sample is not in the training set
        try:
            test = input_tensors[test_sample]
            test = input_tensors[test_sample_aug]
            print(f"FAIL: {test_sample} and/or {test_sample_aug} is in training set")
        except KeyError as e:
            print(f"PASS: {test_sample} and {test_sample_aug} are not in the training set")

    

    # Convert input tensors and labels from dict to list
    input_tensor_list = []
    label_list = []
    for key in input_tensors:
        input_tensor_list.append(input_tensors[key])
        label_list.append(labels[key])

    x = torch.from_numpy(np.array(input_tensor_list, dtype=np.float32))
    y = torch.from_numpy(np.array(label_list, dtype=np.int64))
    print('x:', x.shape)
    print('y:', y.shape)



    if is_test_set:
        test_input_tensors = data_processing.get_data('test_behind_los_pass_aug_input_tensors')
        test_labels = data_processing.get_data('test_behind_los_pass_aug_labels')

        # Convert test input tensors and labels from dict to list
        test_input_tensor_list = []
        test_label_list = []
        for key in test_input_tensors:
            test_input_tensor_list.append(test_input_tensors[key])
            test_label_list.append(test_labels[key])


        test_x = torch.from_numpy(np.array(test_input_tensor_list, dtype=np.float32))
        test_y = torch.from_numpy(np.array(test_label_list, dtype=np.float32))
        print('test_x:', test_x.shape)
        print('test_y:', test_y.shape)


    # TRAIN CNN
    seeds = [42]#, 215, 23, 64]
    all_mean_acc = []
    all_std_acc = []
    for seed in seeds:
        set_seed(seed)
        mean_acc, std_acc, best_acc, best_state = cross_validation(x, y)
        print(f"Mean Cross-Val accuracy: {mean_acc:.3f} += {std_acc:.3f}")
        print(f"Best Accuracy: {best_acc*100:.2f}%")

        all_mean_acc.append(mean_acc)
        all_std_acc.append(std_acc)

    print(f"TOTAL {len(seeds)}-SEED MEAN ACC: {np.mean(all_mean_acc)*100:.2f}% (MEAN STD: {np.mean(all_std_acc)})")


    if is_test_set:

        # SAVE BEST STATE CNN
        best_model = BasicCNN()
        best_model.load_state_dict(best_state)   # best weights
        torch.save(best_model.state_dict(), 'behind_los_success_withheld_model.pt')

        # # LOAD BEST STATE OF CNN
        test_model = BasicCNN()
        test_model.load_state_dict(torch.load('behind_los_success_withheld_model.pt', map_location='cpu'))
        test_model.eval()

        # TEST ON WITHHELD DATA
        # x_test: tensor shape (N, 12, 11, 10)
        # y_test: tensor shape (N,)
        test_dataset   = TensorDataset(test_x, test_y)
        test_loader    = DataLoader(test_dataset, batch_size=256)
        with torch.no_grad():
            logits = test_model(test_x).cpu().numpy()
            probs  = 1 / (1 + np.exp(-logits))
            print('PROBS:', probs)
            preds  = (probs > 0.5).astype(int)


        test_acc = np.mean(preds == test_y.cpu().numpy())
        print("Hold-out accuracy:", test_acc)


        # min_frame = 128
        # max_frame = 176
        for i in range(max_frame - min_frame + 1):
            frame = i+min_frame
            print(f"FRAME {frame}: {probs[i]}")

        for play,play_frames in test_play_frames.items():
            game_id, play_id = play
            play_data = passing_play_data_2021[(passing_play_data_2021['gameId'] == game_id) & (passing_play_data_2021['playId'] == play_id)].iloc[0]
            visualization.create_play_gif(play_data, play_frames, probs, withheld_data[test_sample]['receiver_id'] ,f'{game_id}_{play_id}_behind_los_norm_centered', loop=False, zoom=False)






if __name__ == "__main__":
    main()