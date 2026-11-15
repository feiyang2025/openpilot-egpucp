#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void pose_err_fun(double *nom_x, double *delta_x, double *out_6219666401814639348);
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6870330160140080945);
void pose_H_mod_fun(double *state, double *out_1928910883971935919);
void pose_f_fun(double *state, double dt, double *out_8030521232260507982);
void pose_F_fun(double *state, double dt, double *out_3503743028922815958);
void pose_h_4(double *state, double *unused, double *out_5552913628623474626);
void pose_H_4(double *state, double *unused, double *out_527442235044937530);
void pose_h_10(double *state, double *unused, double *out_249315959449796468);
void pose_H_10(double *state, double *unused, double *out_7948841605243004373);
void pose_h_13(double *state, double *unused, double *out_2639064768667693187);
void pose_H_13(double *state, double *unused, double *out_3739716060377270331);
void pose_h_14(double *state, double *unused, double *out_3162521539941766119);
void pose_H_14(double *state, double *unused, double *out_4490683091384422059);
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt);
}