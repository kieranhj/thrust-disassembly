\ ******************************************************************************
\ ******************************************************************************
\ * Sprite data
\ *
\ * In SWRAM builds this block is replaced by tools/output/object_sprites.asm,
\ * which is owned by tools/sprite_editor.py. Keep inline copy in sync if
\ * non-SWRAM builds are ever revived.
\ ******************************************************************************
\ ******************************************************************************

.obj_sprite_data_A_gun_up_right                ; gun up right
        EQUB    $88,$10,$18,$80,$08,$10,$18,$80
        EQUB    $10,$18,$80,$10,$18,$20,$80,$08
        EQUB    $18,$20,$90,$18,$20,$90,$18,$20
        EQUB    $98,$20,$98,$20,$A0,$A0,$A0,$A0
        EQUB    $A0,$FF
.obj_sprite_data_B_gun_up_right
        EQUB    $66,$77,$88,$11,$99,$88
        EQUB    $66,$66,$66,$11,$88,$11,$88,$88
        EQUB    $FF,$FF,$66,$88,$EE,$11,$88,$11
        EQUB    $88,$66,$66,$11,$11,$11,$99,$99
        EQUB    $55,$55,$33,$FF

.obj_sprite_data_A_gun_down_right            ; gun down right
        EQUB    $20,$A0,$A0,$A0
        EQUB    $A0,$98,$20,$98,$20,$90,$18,$20
        EQUB    $90,$18,$20,$80,$08,$18,$20,$80
        EQUB    $10,$18,$20,$80,$10,$18,$80,$08
        EQUB    $10,$18,$88,$10,$18,$FF
.obj_sprite_data_B_gun_down_right
        EQUB    $33,$55
        EQUB    $55,$99,$99,$11,$11,$66,$11,$11
        EQUB    $88,$66,$EE,$11,$88,$FF,$FF,$66
        EQUB    $88,$88,$11,$88,$88,$66,$66,$11
        EQUB    $11,$99,$88,$66,$66,$77,$88,$FF

.obj_sprite_data_A_gun_up_left                ; gun up left
        EQUB    $88,$10,$18,$88,$10,$18,$20,$88
        EQUB    $10,$20,$80,$08,$10,$20,$80,$08
        EQUB    $18,$20,$80,$08,$10,$80,$08,$10
        EQUB    $80,$08,$80,$08,$80,$80,$80,$80
        EQUB    $80,$FF
.obj_sprite_data_B_gun_up_left
        EQUB    $11,$EE,$66,$66,$11,$99
        EQUB    $88,$88,$66,$66,$11,$11,$88,$11
        EQUB    $11,$66,$FF,$FF,$11,$88,$77,$66
        EQUB    $11,$88,$88,$66,$88,$88,$99,$99
        EQUB    $AA,$AA,$CC,$FF

.obj_sprite_data_A_gun_down_left            ; gun down left
        EQUB    $00,$80,$80,$80,$80,$80,$08,$80
        EQUB    $08,$80,$08,$10,$80,$08,$10,$80
        EQUB    $08,$18,$20,$80,$08,$10,$20,$88
        EQUB    $10,$20,$88,$10,$18,$20,$88,$10
        EQUB    $18,$FF
.obj_sprite_data_B_gun_down_left
        EQUB    $CC,$AA,$AA,$99,$99,$88,$88,$88
        EQUB    $66,$66,$11,$88,$11,$88,$77,$11
        EQUB    $66,$FF,$FF,$11,$11,$88,$11,$88
        EQUB    $66,$66,$66,$11,$99,$88,$11,$EE
        EQUB    $66,$FF
        
.obj_sprite_data_A_fuel                        ; fuel
        EQUB    $00,$08,$10,$18,$80,$18
        EQUB    $80,$18,$80,$08,$10,$18,$80,$08
        EQUB    $10,$18,$80,$08,$10,$18,$80,$08
        EQUB    $10,$18,$80,$08,$10,$18,$80,$18
        EQUB    $80,$18,$80,$08,$10,$18,$88,$10
        EQUB    $80,$08,$10,$18,$80,$18,$FF
.obj_sprite_data_B_fuel
        EQUB    $01
        EQUB    $0F,$0F,$08,$06,$06,$08,$01,$38
        EQUB    $50,$60,$81,$28,$50,$40,$81,$38
        EQUB    $50,$60,$81,$28,$50,$40,$81,$28
        EQUB    $70,$60,$C1,$08,$01,$06,$06,$01
        EQUB    $0F,$0F,$08,$88,$11,$11,$88,$11
        EQUB    $88,$11,$88,$FF

.obj_sprite_data_A_pod_stand                ; pod & stand
        EQUB    $90,$88,$10,$18
        EQUB    $88,$18,$88,$18,$88,$18,$88,$18
        EQUB    $88,$18,$88,$18,$88,$18,$88,$10
        EQUB    $18,$90,$88,$18,$88,$10,$18,$88
        EQUB    $18,$88,$10,$18,$90,$90,$90,$88
        EQUB    $10,$FF
.obj_sprite_data_B_pod_stand
        EQUB    $EE,$33,$11,$88,$44,$44
        EQUB    $44,$44,$88,$22,$88,$22,$88,$22
        EQUB    $44,$44,$44,$44,$33,$11,$88,$EE
        EQUB    $02,$08,$05,$0F,$04,$04,$04,$03
        EQUB    $01,$08,$0A,$0A,$0A,$01,$01,$FF

.obj_sprite_data_A_generator                ; generator
        EQUB    $08,$10,$18,$88,$18,$20,$80,$08
        EQUB    $18,$20,$80,$20,$80,$20,$80,$20
        EQUB    $80,$20,$80,$20,$80,$20,$80,$20
        EQUB    $80,$20,$80,$20,$80,$20,$80,$08
        EQUB    $10,$18,$20,$80,$20,$80,$20,$80
        EQUB    $20,$80,$20,$FF
.obj_sprite_data_B_generator
        EQUB    $01,$0F,$08,$06
        EQUB    $06,$EE,$01,$08,$01,$AA,$02,$AA
        EQUB    $04,$AA,$04,$AA,$08,$AB,$08,$AB
        EQUB    $08,$AB,$08,$AB,$04,$AA,$04,$AA
        EQUB    $02,$AA,$FF,$FF,$FF,$FF,$BB,$88
        EQUB    $11,$B8,$11,$B8,$11,$B8,$11,$FF

.obj_sprite_data_A_door_switch_right        ; door switch right
        EQUB    $80,$80,$08,$88,$88,$88,$88,$88
        EQUB    $88,$88,$88,$88,$88,$80,$08,$80
        EQUB    $FF
.obj_sprite_data_B_door_switch_right
        EQUB    $0E,$01,$08,$04,$02,$02,$01
        EQUB    $01,$01,$01,$02,$02,$04,$01,$08
        EQUB    $0E

.obj_sprite_data_A_door_switch_left            ; door switch left
        EQUB    $88,$80,$08,$80,$80,$80,$80
        EQUB    $80,$80,$80,$80,$80,$80,$80,$08
        EQUB    $88,$FF
.obj_sprite_data_B_door_switch_left
        EQUB    $07,$01,$08,$02,$04,$04
        EQUB    $08,$08,$08,$08,$04,$04,$02,$01
        EQUB    $08,$07

\ ******************************************************************************
\ ******************************************************************************
\ * Data pointers to data & offset blocks for static sprites per object above
\ ******************************************************************************
\ ******************************************************************************

.obj_sprite_data_A_table_LO
        EQUB    LO(obj_sprite_data_A_gun_up_right)
        EQUB    LO(obj_sprite_data_A_gun_down_right)
        EQUB    LO(obj_sprite_data_A_gun_up_left)
        EQUB    LO(obj_sprite_data_A_gun_down_left)
        EQUB    LO(obj_sprite_data_A_fuel)
        EQUB    LO(obj_sprite_data_A_pod_stand)
        EQUB    LO(obj_sprite_data_A_generator)
        EQUB    LO(obj_sprite_data_A_door_switch_right)
        EQUB    LO(obj_sprite_data_A_door_switch_left)

.obj_sprite_data_A_table_HI
        EQUB    HI(obj_sprite_data_A_gun_up_right)
        EQUB    HI(obj_sprite_data_A_gun_down_right)
        EQUB    HI(obj_sprite_data_A_gun_up_left)
        EQUB    HI(obj_sprite_data_A_gun_down_left)
        EQUB    HI(obj_sprite_data_A_fuel)
        EQUB    HI(obj_sprite_data_A_pod_stand)
        EQUB    HI(obj_sprite_data_A_generator)
        EQUB    HI(obj_sprite_data_A_door_switch_right)
        EQUB    HI(obj_sprite_data_A_door_switch_left)

.obj_sprite_data_B_table_LO
        EQUB    LO(obj_sprite_data_B_gun_up_right)
        EQUB    LO(obj_sprite_data_B_gun_down_right)
        EQUB    LO(obj_sprite_data_B_gun_up_left)
        EQUB    LO(obj_sprite_data_B_gun_down_left)
        EQUB    LO(obj_sprite_data_B_fuel)
        EQUB    LO(obj_sprite_data_B_pod_stand)
        EQUB    LO(obj_sprite_data_B_generator)
        EQUB    LO(obj_sprite_data_B_door_switch_right)
        EQUB    LO(obj_sprite_data_B_door_switch_left)

.obj_sprite_data_B_table_HI
        EQUB    HI(obj_sprite_data_B_gun_up_right)
        EQUB    HI(obj_sprite_data_B_gun_down_right)
        EQUB    HI(obj_sprite_data_B_gun_up_left)
        EQUB    HI(obj_sprite_data_B_gun_down_left)
        EQUB    HI(obj_sprite_data_B_fuel)
        EQUB    HI(obj_sprite_data_B_pod_stand)
        EQUB    HI(obj_sprite_data_B_generator)
        EQUB    HI(obj_sprite_data_B_door_switch_right)
        EQUB    HI(obj_sprite_data_B_door_switch_left)
