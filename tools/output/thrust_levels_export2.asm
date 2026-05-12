\ ******************************************************************************
\ ******************************************************************************
\ * Level data - landscape / terrain, objects
\ ******************************************************************************
\ ******************************************************************************

\ ******************************************************************************
\ * Terrain data per level - left count & inc same length, right count & inc same length
\ * Terrain pointers set to left or right wall count & increment arrays
\ ******************************************************************************

.terrain_left_wall_count_0
        EQUB    $FF,$FF,$AB,$01,$0F,$01,$0B,$24,$01,$FF
.terrain_left_wall_inc_0
        EQUB    $00,$00,$00,$55,$01,$15,$01,$00,$1A,$00
.terrain_right_wall_count_0
        EQUB    $FF,$FF,$AB,$01,$09,$01,$FF
.terrain_right_wall_inc_0
        EQUB    $00,$00,$00,$B7,$FF,$F1,$00

.terrain_left_wall_count_1
        EQUB    $FF,$FF,$AF,$01,$0B,$01,$17,$36,$17,$14,$0F,$01,$10,$01,$01,$01,$01,$01,$02,$01,$01,$01,$02,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$09,$01,$0C,$01,$0B,$01,$13,$01,$02,$01,$02,$01,$03,$02,$01,$01,$02,$01,$02,$02,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$2A,$02,$05,$01,$05,$01,$05,$01,$05,$01,$05,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$FF
.terrain_left_wall_inc_1
        EQUB    $00,$00,$00,$4A,$01,$19,$01,$00,$FF,$00,$01,$12,$00,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$00,$FF,$00,$FF,$00,$FF,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$02,$01,$02,$00,$01,$00,$02,$00,$03,$04,$03,$05,$01,$00,$08,$00,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$FE,$FF,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$03,$00
.terrain_right_wall_count_1
        EQUB    $FF,$FF,$AF,$01,$1B,$3A,$11,$15,$17,$01,$01,$10,$04,$01,$08,$01,$08,$01,$04,$01,$01,$07,$01,$06,$01,$07,$01,$07,$01,$05,$01,$09,$01,$01,$01,$02,$02,$02,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$02,$01,$02,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$2B,$02,$01,$06,$01,$04,$01,$06,$01,$04,$01,$06,$01,$04,$01,$03,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$02,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$01,$FF
.terrain_right_wall_inc_1
        EQUB    $00,$00,$00,$B4,$FF,$00,$01,$00,$FF,$FE,$FF,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FE,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$FC,$FF,$00,$FF,$00,$FE,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$00,$01,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00,$FF,$00

.terrain_left_wall_count_2
        EQUB    $FF,$FF,$B9,$01,$50,$0A,$32,$01,$0A,$1E,$01,$0A,$55,$0A,$01,$FF
.terrain_left_wall_inc_2
        EQUB    $00,$00,$00,$87,$00,$FF,$00,$E2,$FF,$00,$F1,$FF,$00,$01,$15,$00
.terrain_right_wall_count_2
        EQUB    $FF,$FF,$B9,$01,$13,$01,$3C,$01,$14,$0A,$01,$3C,$01,$32,$01,$09,$FF
.terrain_right_wall_inc_2
        EQUB    $00,$00,$00,$B4,$00,$E9,$00,$18,$00,$FF,$EC,$00,$E2,$00,$EC,$FF,$00

.terrain_left_wall_count_3
        EQUB    $FF,$FF,$A0,$01,$13,$01,$15,$26,$14,$0A,$06,$14,$22,$01,$14,$01,$26,$1C,$24,$0A,$FF
.terrain_left_wall_inc_3
        EQUB    $00,$00,$00,$5A,$01,$11,$00,$FF,$00,$01,$00,$FF,$00,$19,$01,$21,$00,$FF,$00,$01,$00
.terrain_right_wall_count_3
        EQUB    $FF,$FF,$A0,$01,$67,$01,$12,$18,$01,$84,$18,$14,$01,$FF
.terrain_right_wall_inc_3
        EQUB    $00,$00,$00,$8D,$00,$E2,$00,$01,$28,$00,$FF,$00,$F4,$00

.terrain_left_wall_count_4
        EQUB    $FF,$FF,$A5,$01,$15,$16,$01,$38,$01,$0C,$1C,$01,$28,$14,$01,$56,$14,$0E,$01,$1C,$0C,$01,$1E,$0C,$01,$52,$08,$01,$FF
.terrain_left_wall_inc_4
        EQUB    $00,$00,$00,$58,$01,$00,$17,$00,$F6,$FF,$00,$0A,$00,$FF,$EC,$00,$01,$00,$F6,$00,$01,$12,$00,$01,$14,$00,$01,$0A,$00
.terrain_right_wall_count_4
        EQUB    $FF,$FF,$A5,$01,$64,$01,$0A,$1E,$01,$28,$01,$28,$0A,$01,$22,$20,$2C,$01,$0A,$16,$01,$3E,$10,$1E,$0C,$FF
.terrain_right_wall_inc_4
        EQUB    $00,$00,$00,$93,$00,$0E,$01,$00,$DC,$00,$08,$00,$FF,$DE,$00,$01,$00,$0A,$01,$00,$10,$00,$01,$00,$FF,$00

.terrain_left_wall_count_5
        EQUB    $FF,$FF,$7F,$01,$3E,$01,$50,$28,$01,$0A,$A2,$01,$36,$0D,$14,$36,$0E,$0D,$1F,$0A,$39,$01,$FF
.terrain_left_wall_inc_5
        EQUB    $00,$00,$00,$4D,$00,$17,$01,$00,$EC,$FF,$00,$EF,$00,$FF,$00,$01,$00,$FF,$00,$FF,$00,$0B,$00
.terrain_right_wall_count_5
        EQUB    $FF,$FF,$7F,$01,$2B,$14,$37,$41,$14,$14,$01,$1C,$22,$12,$14,$0A,$32,$01,$27,$2C,$1E,$07,$07,$38,$1C,$23,$01,$16,$01,$FF
.terrain_right_wall_inc_5
        EQUB    $00,$00,$00,$B7,$FF,$00,$01,$00,$01,$00,$E7,$FF,$00,$01,$00,$FF,$00,$EB,$00,$01,$00,$01,$FF,$00,$FF,$00,$0D,$00,$F1,$00

\ ******************************************************************************
\ * Level object data
\ ******************************************************************************

.level_0_obj_pos_X
        EQUB    $8F,$A0,$6E,$7C,$5B,$8A,$7E,$60,$61,$9C
.level_0_obj_pos_Y
        EQUB    $BD,$AB,$B3,$BA,$AD,$7F,$7F,$74,$64,$B7
.level_0_obj_pos_Y_EXT
        EQUB    $01,$01,$01,$01,$01,$01,$01,$01,$01,$01
.level_0_obj_type
        EQUB    $05,$06,$04,$09,$00,$0E,$0E,$0F,$0F,$08,$FF
.level_0_obj_data_0
        EQUB    $00,$00,$00,$F0,$02,$80,$00,$FF,$79,$00
.level_0_obj_data_1
        EQUB    $00,$00,$00,$77,$00,$20,$10,$15,$20,$00
.level_0_obj_data_2
        EQUB    $00,$00,$00,$F4,$00,$00,$00,$00,$00,$00

.level_1_obj_pos_X
        EQUB    $81,$64,$8D,$73,$75,$9C,$99,$A5,$A3,$91
.level_1_obj_pos_Y
        EQUB    $38,$B1,$BC,$34,$13,$09,$31,$9C,$99,$4A
.level_1_obj_pos_Y_EXT
        EQUB    $02,$01,$02,$02,$02,$02,$02,$01,$02,$03
.level_1_obj_type
        EQUB    $05,$06,$04,$09,$0A,$0C,$0B,$10,$10,$10,$FF
.level_1_obj_data_0
        EQUB    $00,$00,$00,$8C,$80,$84,$88,$01,$02,$00
.level_1_obj_data_1
        EQUB    $00,$00,$00,$39,$75,$A0,$AB,$00,$00,$00
.level_1_obj_data_2
        EQUB    $00,$00,$00,$A5,$45,$EE,$AB,$00,$00,$00

.level_2_obj_pos_X
        EQUB    $4E,$A4,$78,$97,$9D,$A3,$7D,$67,$81,$AC,$58,$5D,$3E
.level_2_obj_pos_Y
        EQUB    $CE,$C3,$B1,$21,$21,$21,$5E,$91,$0A,$1C,$48,$98,$72
.level_2_obj_pos_Y_EXT
        EQUB    $02,$01,$01,$02,$02,$02,$02,$02,$02,$02,$02,$02,$02
.level_2_obj_type
        EQUB    $05,$06,$04,$04,$04,$04,$04,$04,$0A,$0B,$0A,$0B,$0A,$FF
.level_2_obj_data_0
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$04,$16,$0A,$1B,$06
.level_2_obj_data_1
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$3C,$C4,$3C,$C4,$3C
.level_2_obj_data_2
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$1E,$E2,$1E,$E2,$1E

.level_3_obj_pos_X
        EQUB    $8E,$5B,$AC,$AC,$92,$72,$5A,$5A,$78,$6D,$8A,$A2,$4E,$8A
.level_3_obj_pos_Y
        EQUB    $D9,$40,$51,$87,$57,$D0,$01,$16,$24,$4C,$92,$BA,$32,$EB
.level_3_obj_pos_Y_EXT
        EQUB    $02,$02,$02,$02,$02,$01,$02,$02,$02,$02,$02,$02,$02,$01
.level_3_obj_type
        EQUB    $05,$06,$08,$08,$04,$01,$00,$01,$03,$00,$01,$02,$07,$08,$FF
.level_3_obj_data_0
        EQUB    $00,$00,$00,$00,$00,$06,$06,$06,$12,$1F,$06,$1E,$00,$00
.level_3_obj_data_1
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
.level_3_obj_data_2
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00

.level_4_obj_pos_X
        EQUB    $A2,$8F,$A4,$98,$7C,$9A,$A0,$68,$69,$6F,$89,$8F,$72,$A2,$86,$5D,$8E,$7B,$AC
.level_4_obj_pos_Y
        EQUB    $8D,$29,$25,$75,$C9,$2B,$2B,$87,$0A,$0A,$35,$35,$0D,$0C,$83,$04,$00,$2F,$63
.level_4_obj_pos_Y_EXT
        EQUB    $03,$02,$03,$03,$01,$02,$02,$02,$03,$03,$03,$03,$02,$02,$02,$03,$03,$03,$03
.level_4_obj_type
        EQUB    $05,$06,$08,$07,$04,$04,$04,$04,$04,$04,$04,$04,$01,$03,$02,$00,$03,$00,$03,$FF
.level_4_obj_data_0
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$05,$14,$1A,$02,$12,$1E,$19
.level_4_obj_data_1
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
.level_4_obj_data_2
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00

.level_5_obj_pos_X
        EQUB    $9A,$A9,$A1,$BE,$9A,$C1,$AF,$9B,$A2,$9B,$7B,$AC,$AC,$AC,$CA,$99,$99
.level_5_obj_pos_Y
        EQUB    $E4,$04,$98,$5D,$F8,$57,$BF,$AC,$86,$2E,$1F,$C1,$A8,$67,$3E,$39,$CC
.level_5_obj_pos_Y_EXT
        EQUB    $03,$04,$03,$03,$02,$02,$03,$03,$03,$03,$03,$02,$02,$02,$02,$02,$01
.level_5_obj_type
        EQUB    $05,$06,$07,$08,$04,$04,$02,$01,$01,$03,$01,$02,$03,$02,$03,$01,$03,$FF
.level_5_obj_data_0
        EQUB    $00,$00,$00,$00,$00,$00,$1A,$06,$09,$12,$06,$16,$12,$1B,$12,$05,$0E
.level_5_obj_data_1
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
.level_5_obj_data_2
        EQUB    $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00

\ ******************************************************************************
\ * Gravity values per level
\ ******************************************************************************

.level_gravity_FRAC_table
        EQUB    $05,$07,$09,$0B,$0C,$0D

\ ******************************************************************************
\ * Y-banded parameter overrides per level
\ * Three parallel arrays: band_y_HI, band_y_LO, band_gravity (gravity_FRAC).
\ * Bands sorted ascending by Y. Sentinel: $FF in band_y_HI terminates list.
\ ******************************************************************************

.level_0_band_y_HI
        EQUB    $FF
.level_0_band_y_LO
        EQUB    $00
.level_0_band_gravity
        EQUB    $00
.level_0_band_landscape_colour
        EQUB    $FF
.level_0_band_object_colour
        EQUB    $FF

.level_1_band_y_HI
        EQUB    $02,$02,$02,$FF
.level_1_band_y_LO
        EQUB    $04,$4C,$D8,$00
.level_1_band_gravity
        EQUB    $0E,$F8,$07,$00
.level_1_band_landscape_colour
        EQUB    $05,$01,$06,$FF
.level_1_band_object_colour
        EQUB    $06,$02,$02,$FF

.level_2_band_y_HI
        EQUB    $FF
.level_2_band_y_LO
        EQUB    $00
.level_2_band_gravity
        EQUB    $00
.level_2_band_landscape_colour
        EQUB    $FF
.level_2_band_object_colour
        EQUB    $FF

.level_3_band_y_HI
        EQUB    $FF
.level_3_band_y_LO
        EQUB    $00
.level_3_band_gravity
        EQUB    $00
.level_3_band_landscape_colour
        EQUB    $FF
.level_3_band_object_colour
        EQUB    $FF

.level_4_band_y_HI
        EQUB    $FF
.level_4_band_y_LO
        EQUB    $00
.level_4_band_gravity
        EQUB    $00
.level_4_band_landscape_colour
        EQUB    $FF
.level_4_band_object_colour
        EQUB    $FF

.level_5_band_y_HI
        EQUB    $FF
.level_5_band_y_LO
        EQUB    $00
.level_5_band_gravity
        EQUB    $00
.level_5_band_landscape_colour
        EQUB    $FF
.level_5_band_object_colour
        EQUB    $FF

\ ******************************************************************************
\ * Switch wiring tables per level
\ * Five parallel arrays per level, indexed by switch slot:
\ *   level_N_switch_obj_indices: object index of each switch ($FF terminator)
\ *   level_N_switch_target:     target object index ($FF = no target / disabled)
\ *   level_N_switch_action:     action code (see thrust.6502)
\ *   level_N_switch_arg_a:      action arg A (e.g. obj_data slot 0..2 for set_param/xor_param)
\ *   level_N_switch_arg_b:      action arg B (e.g. value or XOR mask)
\ ******************************************************************************

.level_0_switch_obj_indices
        EQUB    $09,$09,$09,$FF
.level_0_switch_target
        EQUB    $03,$03,$02,$FF
.level_0_switch_action
        EQUB    $07,$07,$04,$00
.level_0_switch_arg_a
        EQUB    $02,$01,$00,$00
.level_0_switch_arg_b
        EQUB    $80,$80,$00,$00

.level_1_switch_obj_indices
        EQUB    $FF
.level_1_switch_target
        EQUB    $FF
.level_1_switch_action
        EQUB    $00
.level_1_switch_arg_a
        EQUB    $00
.level_1_switch_arg_b
        EQUB    $00

.level_2_switch_obj_indices
        EQUB    $FF
.level_2_switch_target
        EQUB    $FF
.level_2_switch_action
        EQUB    $00
.level_2_switch_arg_a
        EQUB    $00
.level_2_switch_arg_b
        EQUB    $00

.level_3_switch_obj_indices
        EQUB    $02,$0C,$0D,$FF
.level_3_switch_target
        EQUB    $04,$07,$05,$FF
.level_3_switch_action
        EQUB    $04,$04,$03,$00
.level_3_switch_arg_a
        EQUB    $00,$00,$00,$00
.level_3_switch_arg_b
        EQUB    $00,$00,$00,$00

.level_4_switch_obj_indices
        EQUB    $FF
.level_4_switch_target
        EQUB    $FF
.level_4_switch_action
        EQUB    $00
.level_4_switch_arg_a
        EQUB    $00
.level_4_switch_arg_b
        EQUB    $00

.level_5_switch_obj_indices
        EQUB    $FF
.level_5_switch_target
        EQUB    $FF
.level_5_switch_action
        EQUB    $00
.level_5_switch_arg_a
        EQUB    $00
.level_5_switch_arg_b
        EQUB    $00

\ ******************************************************************************
\ * No-wrap Y threshold per level
\ * X wrap disabled when player Y >= this value ($FFFF = always wrap)
\ ******************************************************************************

.level_no_wrap_y_table_LO
        EQUB    $FF,$FF,$FF,$FF,$FF,$FF
.level_no_wrap_y_table_HI
        EQUB    $FF,$FF,$FF,$FF,$FF,$FF

\ ******************************************************************************
\ * Level colours
\ ******************************************************************************

.level_landscape_colour
        EQUB    $01,$02,$06,$02,$01,$05
.level_object_colour
        EQUB    $02,$01,$02,$05,$05,$06

\ ******************************************************************************
\ * Level reset data - respawn checkpoints
\ * Struct-of-arrays: Y_HI, Y_LO, win_X, win_Y_EXT, win_Y, spawn_X
\ ******************************************************************************

.level_reset_data_sizes
        EQUB    $01,$03,$03,$03,$04,$05

.level_0_reset_data
        EQUB    $01
        EQUB    $9C
        EQUB    $56
        EQUB    $01
        EQUB    $24
        EQUB    $6C

.level_1_reset_data
        EQUB    $01,$02,$03
        EQUB    $91,$73,$21
        EQUB    $56,$5E,$6B
        EQUB    $01,$01,$02
        EQUB    $24,$F0,$A1
        EQUB    $6C,$7E,$8C

.level_2_reset_data
        EQUB    $01,$02,$02
        EQUB    $91,$2D,$96
        EQUB    $56,$6F,$32
        EQUB    $01,$01,$02
        EQUB    $24,$AA,$23
        EQUB    $6C,$86,$48

.level_3_reset_data
        EQUB    $01,$01,$02
        EQUB    $91,$E6,$4A
        EQUB    $56,$57,$76
        EQUB    $01,$01,$01
        EQUB    $24,$60,$D8
        EQUB    $6C,$7B,$A1

.level_4_reset_data
        EQUB    $01,$02,$02,$03
        EQUB    $91,$68,$DC,$15
        EQUB    $56,$58,$43,$64
        EQUB    $01,$01,$02,$02
        EQUB    $24,$EE,$66,$9F
        EQUB    $6C,$7B,$6B,$81

.level_5_reset_data
        EQUB    $01,$02,$02,$03,$03
        EQUB    $91,$4B,$D4,$2A,$98
        EQUB    $56,$8C,$82,$6E,$87
        EQUB    $01,$01,$02,$02,$03
        EQUB    $24,$D8,$5A,$B4,$1B
        EQUB    $6C,$A2,$9A,$87,$AE

.level_reset_ptr_table_LO
        EQUB    LO(level_0_reset_data)
        EQUB    LO(level_1_reset_data)
        EQUB    LO(level_2_reset_data)
        EQUB    LO(level_3_reset_data)
        EQUB    LO(level_4_reset_data)
        EQUB    LO(level_5_reset_data)
.level_reset_ptr_table_HI
        EQUB    HI(level_0_reset_data)
        EQUB    HI(level_1_reset_data)
        EQUB    HI(level_2_reset_data)
        EQUB    HI(level_3_reset_data)
        EQUB    HI(level_4_reset_data)
        EQUB    HI(level_5_reset_data)

.level_reset_ptr2_table_LO
        EQUB    LO(level_0_reset_data + 1)
        EQUB    LO(level_1_reset_data + 3)
        EQUB    LO(level_2_reset_data + 3)
        EQUB    LO(level_3_reset_data + 3)
        EQUB    LO(level_4_reset_data + 4)
        EQUB    LO(level_5_reset_data + 5)
.level_reset_ptr2_table_HI
        EQUB    HI(level_0_reset_data + 1)
        EQUB    HI(level_1_reset_data + 3)
        EQUB    HI(level_2_reset_data + 3)
        EQUB    HI(level_3_reset_data + 3)
        EQUB    HI(level_4_reset_data + 4)
        EQUB    HI(level_5_reset_data + 5)
