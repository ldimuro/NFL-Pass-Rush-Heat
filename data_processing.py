import pandas as pd
from pandas import DataFrame
import numpy as np
import constants
import math
import re
import pickle
from itertools import product


def filter_tracking_data(tracking_data, passing_play_data):
    filtered_tracking_data = []

    # Filter out all tracking data for plays that are not included in 'passing_play_data'
    for week_df in tracking_data:
        merged = week_df.merge(passing_play_data[['gameId', 'playId']], on=['gameId', 'playId'], how='inner')
        filtered_tracking_data.append(merged)

    return filtered_tracking_data


def normalize_field_direction(tracking_data):
    normalized_tracking_data = []

    # Flip spatial features so that offense is always going from left-to-right
    for week_df in tracking_data:
        week_df = week_df.copy()

        left_mask = week_df['playDirection'] == 'left'
        week_df.loc[left_mask, 'x'] = constants.FIELD_LENGTH - week_df.loc[left_mask, 'x']
        week_df.loc[left_mask, 'o'] = (360 - week_df.loc[left_mask, 'o']) % 360
        week_df.loc[left_mask, 'dir'] = (360 - week_df.loc[left_mask, 'dir']) % 360
        week_df.loc[left_mask, 'playDirection'] = 'right_norm'

        normalized_tracking_data.append(week_df)

    return normalized_tracking_data


def normalize_to_center(tracking_data: DataFrame):
    normalized_weeks = []
    
    for week_df in tracking_data:
        week_df = week_df.copy()
        normalized_plays = []

        # Group by each play (gameId + playId)
        for (game_id, play_id), play_df in week_df.groupby(['gameId', 'playId']):
            ball_rows = play_df[play_df['team' if 'team' in week_df.columns else 'club'] == 'football']
            if ball_rows.empty:
                normalized_plays.append(play_df)
                continue

            # Calculate shift to move ball x to 60
            ball_x = ball_rows.iloc[0]['x']
            shift_x = 60 - ball_x

            play_df['x'] = play_df['x'] + shift_x
            normalized_plays.append(play_df)

        # Combine all normalized plays back into one DataFrame for the week
        normalized_weeks.append(pd.concat(normalized_plays, ignore_index=True))

    return normalized_weeks


def flip_play_and_jitter(tracking_frame: DataFrame, noise_scale=0.2):
    track_frame_df = tracking_frame.copy()

    # 1. Horizontal mirror
    track_frame_df['x']  = constants.FIELD_LENGTH - track_frame_df['x']
    track_frame_df['o']  = (360 - track_frame_df['o']) % 360
    track_frame_df['dir'] = (360 - track_frame_df['dir']) % 360

    # 2. Small jitter
    noise = np.random.normal(0, noise_scale, size=(len(track_frame_df), 4))
    track_frame_df['x']  += noise[:, 0]
    track_frame_df['y']  += noise[:, 1]
    track_frame_df['o']  = (track_frame_df['o']  + noise[:, 2]) % 360
    track_frame_df['dir'] = (track_frame_df['dir'] + noise[:, 3]) % 360

    return track_frame_df


def augment_data(data):
    data_mirrored_jittered = {}#data.copy()
    
    for play,play_data in data.items():
        game_id, play_id = play
        play_id += 0.1  # add 0.1 to ID to mark it as "augmented"

        flipped_jittered_tracking_data = flip_play_and_jitter(play_data['tracking_data'])
        data_mirrored_jittered[(game_id, play_id)] = play_data
        data_mirrored_jittered[(game_id, play_id)]['tracking_data'] = flipped_jittered_tracking_data

    return data_mirrored_jittered



def get_relevant_frames(play_data: DataFrame, tracking_data: DataFrame, start_events, end_events, extra_frames=0):
    play_tracking_dict = {}

    # Collapse all weeks of tracking data into 1 DataFrame
    tracking_data = pd.concat(tracking_data, ignore_index=True)

    for i,row in play_data.iterrows():
        game_id = row['gameId']
        play_id = row['playId']

        print(f'searching for {game_id} - {play_id}')

        # Look through all weeks of tracking data for specific play
        tracking_play = None
        match = tracking_data[(tracking_data['gameId'] == game_id) & (tracking_data['playId'] == play_id)]
        
        if not match.empty:
            tracking_play = match.sort_values('frameId')

        # Remove all frames before start_events and after end_events
        if tracking_play is not None:

            # Plays will either start with 'huddle_break_offense' or NA
            if 'START' in start_events:
                start_index = tracking_play[(tracking_play['event'].isin(['huddle_break_offense'])) | (tracking_play['event'].isna())].index
            else:
                start_index = tracking_play[tracking_play['event'].isin(start_events)].index

            # Plays will end with NA
            if 'END' in end_events:
                end_index = tracking_play[tracking_play['event'].isna()].index
            else:
                end_index = tracking_play[tracking_play['event'].isin(end_events)].index

            if not start_index.empty and not end_index.empty:
                tracking_play = tracking_play.loc[start_index[0]:end_index[-1]].reset_index(drop=True)
            else:
                print(f"🚨Warning: Missing event in play ({game_id},{play_id})")

            # Add all relevant tracking frames to plays dict
            play_tracking_dict[(game_id, play_id)] = tracking_play
            # print(f'processed tracking frames for {game_id} - {play_id}')
        else:
            print(f'🚨could not find {game_id} - {play_id}')

    return play_tracking_dict



def get_data_at_pass_forward(play_data: DataFrame, tracking_data: DataFrame, player_data: DataFrame):
    # Consolidate all tracking_weeks together
    tracking_data = pd.concat(tracking_data, ignore_index=True)

    # Extract first and last name of receiver of a play in the playDescription and create 2 new columns for the name
    play_data[['receiver_first_initial', 'receiver_last_name']] = play_data['playDescription'].apply(lambda desc: pd.Series(extract_first_and_last_name(desc)))

    # For each passing play:
    # 1) use first and last name to obtain the nflId of the receiver
    # 2) extract the tracking data at the moment of the pass for all 22 players on the field
    # 3) store the receiver_id and tracking data in a dictionary (with (gameId, playId) as the key)
    candidate_plays = {}
    skipped = 0
    for i,play in play_data.iterrows():
        game_id = play['gameId']
        play_id = play['playId']
        play_df = tracking_data[(tracking_data['gameId'] == game_id) & (tracking_data['playId'] == play_id)]
        los = np.round(play_df[play_df['team'] == 'football'].iloc[0]['x'] if ('club' not in play_df.columns or play_df['club'].isna().all()) else play_df[play_df['club'] == 'football'].iloc[0]['x'])
        receiver_id, all_22_tracking_features = get_receiver_nflId(play, player_data, tracking_data)

        # print(f"\t{game_id},{play_id} receiver: {receiver_id}")

        # receiver_id = None indicates pre-processing issue, so just skip
        try:
            # if receiver_id != None:
            receiver_x_at_pass = np.round(
                all_22_tracking_features[
                    (all_22_tracking_features['nflId'] == receiver_id) &
                    (all_22_tracking_features['event'].isin(['pass_forward', 'pass_shovel', 'autoevent_passforward']))
                ].iloc[0]['x']
            )

            # print('\treceiver_x_at_pass:', receiver_x_at_pass)
            # print('\tLoS:', los)

            # Only store plays in which the receiver is at or behind the LoS at the moment of the pass
            if receiver_x_at_pass - los <= 2:
                print(f"{game_id},{play_id} - LOS:{los}, RECEIVER X (at pass_forward): {receiver_x_at_pass}, result:{play['yardsGained' if 'yardsGained' in play.index else 'prePenaltyPlayResult']}") # playResult for 2018 data
                candidate_plays[(game_id, play_id)] = {
                        'receiver_id': receiver_id, 
                        'los': los,
                        'receiver_x': receiver_x_at_pass,
                        'down': play['down'],
                        'yardsToGo': play['yardsToGo'],
                        'yardsGained': play['yardsGained' if 'yardsGained' in play.index else 'prePenaltyPlayResult'], # playResult for 2018 data
                        'label': estimate_play_success(play),
                        'play_data': play,
                        'tracking_data': all_22_tracking_features
                }
        except:
            print('skipped!')
            skipped += 1
            continue
    
    print('TOTAL SKIPPED:', skipped)
    return candidate_plays




# Extract first name initial(s) and last name from playDescription
# Can handle cases such as "H.Henry", "Mi.Carter", and "A.St. Brown"
def extract_first_and_last_name(description):
    match = re.search(r'\bto\s+([A-Z][a-z]?)\.([A-Z][a-z]*(?:\.?\s?[A-Z][a-z]*)*)', description)
    if match:
        initials = match.group(1).strip()
        last_name = match.group(2).strip()
        return initials, last_name
    return None, None


def get_receiver_nflId(row, player_data: DataFrame, tracking_data: DataFrame):
    first_initial = row['receiver_first_initial']
    last_name = row['receiver_last_name']
    team = row['possessionTeam']
    game_id = row['gameId']
    play_id = row['playId']

    if pd.isnull(last_name):
        return None, None
    
    # Find frameId at the moment of the pass
    play_df = tracking_data[(tracking_data['gameId'] == game_id) & (tracking_data['playId'] == play_id)]
    pass_forward_frame_id = play_df[play_df['event'].isin(['pass_forward', 'pass_shovel', 'autoevent_passforward'])]['frameId'].min()

    # Get the spatiotemportal data of all 22 players at the moment of the pass
    all_22_tracking_features = play_df[play_df['frameId'] == pass_forward_frame_id]

    # Find player with a matching first initial and last name (case-insensitive)
    matches = player_data[
        (player_data['displayName'].str.startswith(first_initial)) &
        (player_data['displayName'].str.contains(fr'\b{re.escape(last_name)}\b', case=False, na=False))
    ]

    receiver_id = None
    if not matches.empty and len(matches) == 1: # 1 existing player with first initial and last name
        receiver_id = matches.iloc[0]['nflId']
    elif not matches.empty and len(matches) > 1: # more than 1 existing player with first initial and last name

        # Filter to only include players on offense who could receive the ball
        eligible_positions = ['WR', 'TE', 'RB', 'FB']
        # print('player_data:\n', player_data)

        skill_players_df = player_data[player_data['position'].isin(eligible_positions)]

        # Drop 'position' if it exists to prevent merge conflicts
        if 'position' in play_df.columns:
            play_df = play_df.drop(columns=['position'])
        merged_df = play_df.merge(skill_players_df[['nflId', 'position']], on='nflId', how='left')
        # print(merged_df)

        possible_targets_df = merged_df[merged_df['position'].isin(eligible_positions)]
        possible_targets_df = possible_targets_df[(possible_targets_df['frameId'] == pass_forward_frame_id)]# & (possible_targets_df['club'] == team)]
        # print('possible_targets:\n', possible_targets_df)

        # Check for matches in this small subset, instead of all_players
        matches_in_possible_targets = matches[matches['nflId'].isin(possible_targets_df['nflId'])]['nflId'].values

        if len(matches_in_possible_targets) == 1:
            receiver_id = matches_in_possible_targets[0]

    return receiver_id, all_22_tracking_features




def estimate_play_success(play_data: DataFrame):
    down = play_data['down']

    yards_to_go = play_data['yardsToGo']
    yards_gained = play_data['yardsGained' if 'yardsGained' in play_data.index else 'playResult']
    yards_ratio = yards_gained / yards_to_go

    # Play succeeds if:
    #   40% of yardsToGo gained on 1st down
    #   60% of yardsToGo gained on 2nd down
    #   100% of yardsToGo gained on 3rd/4th down
    is_success = False
    if down == 1:
        is_success = True if yards_ratio >= 0.4 else False
    elif down == 2:
        is_success = True if yards_ratio >= 0.6 else False
    else:
        is_success = True if yards_ratio >= 1.0 else False
    
    return is_success


def normalize_yards_to_go(yards_to_go):
    # Range of Down & 0.5-30 yards to go
    min = 0.5
    max = 30
    norm = (yards_to_go - min) / (max - min)
    return norm


def normalize_receiver_position(receiver_position):
    # 1 of 5 possible values: RB, WR, TE, FB, Other
    positions = ['RB', 'WR', 'TE', 'FB']
    pos_val = 0

    if receiver_position in positions:
        pos_val = positions.index(receiver_position)
    else:
        pos_val = len(positions)    # is it len(positions+1)?

    return pos_val / len(positions) # is it len(positions+1)?



def create_input_tensor(play_data, player_data):
    down = play_data['down']
    down_norm = down / 3.0  # 1st, 2nd, 3rd/4th downs

    yards_to_go_norm = normalize_yards_to_go(play_data['yardsToGo'])

    players_on_field = play_data['tracking_data']
    players_on_field = players_on_field[players_on_field['nflId'].notna()] # remove 'football' from tracking_data

    receiver_id = play_data['receiver_id']
    receiver = players_on_field[players_on_field['nflId'] == receiver_id].iloc[0]

    # Get receiver position
    receiver_pos_norm = normalize_receiver_position(player_data[player_data['nflId'] == receiver_id]['position'].iloc[0])

    # Remove the receiver from the tracking_data
    players_without_receiver = players_on_field[players_on_field['nflId'] != receiver_id]
    
    # Drop 'position' if it exists to prevent merge conflicts
    if 'position' in players_without_receiver.columns:
        players_without_receiver = players_without_receiver.drop(columns=['position'])

    # Merge tracking_data with player positions in player_data
    merged_df = players_without_receiver.merge(player_data[['nflId', 'position']], on='nflId', how='left')

    #  Filter offensive and defensive players based on position
    off_players = merged_df[merged_df['position'].isin(constants.OFF_POSITIONS)].copy()
    def_players = merged_df[merged_df['position'].isin(constants.DEF_POSITIONS)].copy()

    # Get velocity of every player (including the receiver)
    player_vel = {}
    for i,player in players_on_field.iterrows():
        player_nflId = player['nflId']
        player_speed = player['dis'] * 10 #player['s']
        player_dir = np.deg2rad(player['dir']) # TODO: Is this right?
        player_v_x = player_speed * np.cos(player_dir) # TODO: is it x=cos, y=sin, or vice versa?
        player_v_y = player_speed * np.sin(player_dir)

        player_vel[player_nflId] = (player_v_x, player_v_y)

    # Calculate relative positions and velocities of every defender to receiver
    def_rel_pos = {}
    def_rel_vel = {}
    for i,defender in def_players.iterrows():
        rel_pos = (defender['x'] - receiver['x'], defender['y'] - receiver['y'])
        rel_vel = (player_vel[defender['nflId']][0] - player_vel[receiver_id][0], 
                   player_vel[defender['nflId']][1] - player_vel[receiver_id][1])

        def_rel_pos[defender['nflId']] = rel_pos
        def_rel_vel[defender['nflId']] = rel_vel

    
    # Calculate relative positions and velocities of every pair of offensive/defensive players (excluding receiver)
    off_def_pair_pos = {}
    off_def_pair_vel = {}
    for off_player, def_player in product(off_players.itertuples(index=False), def_players.itertuples(index=False)):
        diff_pos = (off_player.x - def_player.x, off_player.y - def_player.y)
        diff_vel = (player_vel[off_player.nflId][0] - player_vel[def_player.nflId][0], 
                    player_vel[off_player.nflId][1] - player_vel[def_player.nflId][1])
        
        off_def_pair_pos[(off_player.nflId, def_player.nflId)] = diff_pos
        off_def_pair_vel[(off_player.nflId, def_player.nflId)] = diff_vel
        

    # CONSTRUCT TENSOR
    ############################################################################################################

    # FEATURES:
    # 1) def velocity (v_x, v_y)
    # 2) def position relative to receiver (x,y)
    # 3) def velocity relative to receiver (v_x, v_y)
    # 4) off - def position (x,y)
    # 5) off - def velocity (v_x, v_y)
    # 6) down (0.33, 0.67, 1.0) - 1st/2nd/3rd-4th downs
    # 7) yardsToGo (normalized)
    # 8) receiver position (normalized)

    num_features = (5 * 2) + 3  # 5 features with (x,y) values + feature for "down" + feature for "yardsToGo" + feature for "receiver_position"
    def_count = 11
    off_count = 10
    tensor = np.zeros((num_features, def_count, off_count))

    for i, def_player in enumerate(def_players.itertuples(index=False)):
        def_nflId = def_player.nflId

        # Get features relative to receiver
        def_v_x, def_v_y = player_vel[def_nflId]
        rel_pos_x, rel_pos_y = def_rel_pos[def_nflId]
        rel_vel_x, rel_vel_y = def_rel_vel[def_nflId]

        for j, off_player in enumerate(off_players.itertuples(index=False)):
            off_nflId = off_player.nflId

            # Get features between defender and current offensive player
            off_def_rel_pos_x, off_def_rel_pos_y = off_def_pair_pos[(off_nflId, def_nflId)]
            off_def_rel_vel_x, off_def_rel_vel_y = off_def_pair_vel[(off_nflId, def_nflId)]

            # Fill tensor for current (def_player, off_player) pair

            # Channels 0-1: def velocity (v_x, v_y)
            tensor[0, i, j] = def_v_x
            tensor[1, i, j] = def_v_y

            # Channels 2-3: def position relative to receiver (x,y)
            tensor[2, i, j] = rel_pos_x
            tensor[3, i, j] = rel_pos_y

            # Channel 4-5: def velocity relative to receiver (v_x, v_y)
            tensor[4, i, j] = rel_vel_x
            tensor[5, i, j] = rel_vel_y

            # Channel 6-7: off - def position (x,y)
            tensor[6, i, j] = off_def_rel_pos_x
            tensor[7, i, j] = off_def_rel_pos_y

            # Channel 8-9: off - def velocity (v_x, v_y)
            tensor[8, i, j] = off_def_rel_vel_x
            tensor[9, i, j] = off_def_rel_vel_y

    # Channel 10: normalized down value
    tensor[10, :, :] = down_norm

    # Channel 11: normalized yardsToGo
    tensor[11, :, :] = yards_to_go_norm

    # Channel 12: normalized receiver position
    tensor[12, :, :] = receiver_pos_norm

    return tensor



def get_tensor_batch(input_data, all_players):
    input_tensors = {}
    labels = {}
    skipped = []
    for play,play_data in input_data.items():
        game_id, play_id = play

        # Occasionally there are more/less than 11 players on each side, catch this error and skip
        try:
            # Create input tensor
            tensor = create_input_tensor(play_data, all_players)
            input_tensors[play] = tensor

            # Save corresponding label to input tensor
            label = int(play_data['label'])
            labels[play] = label

            # print(f"created tensor+label for ({game_id},{play_id})")

        except Exception as e:
            skipped.append(play)
            print(f"ERROR FOR ({game_id},{play_id}): {e}")

    print('skipped:', len(skipped))
    print('FINAL TENSOR COUNT:', len(input_tensors)) # 7683 total input tensors
    print('FINAL LABEL COUNT:', len(labels))

    return input_tensors, labels




def save_data(data, file_name):
    with open(f"{file_name}.pkl", 'wb') as f:
        pickle.dump(data, f)


def get_data(file_name):
    with open(f"{file_name}.pkl", 'rb') as f:
        data = pickle.load(f)
    return data



def scale_player_coordinates(player_x, player_y, x_scale=128/constants.FIELD_LENGTH, y_scale=64/constants.FIELD_WIDTH):
    x_scaled = player_x * x_scale
    y_scaled = player_y * y_scale
    return x_scaled, y_scaled


